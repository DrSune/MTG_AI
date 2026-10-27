"""Kill test K2: does a chooser that reads components make unseen cards' choices well?

    MTG_REPO=<tree> .venv/bin/python tools/k2/train.py --data DIR --out FILE.json

Reads ``k2_<SET>.jsonl`` from tools/k2/gen.py. Each row is one engine-labelled choice: the board
before it, the options, and the board after each option. The reading rules are in
``reports/k2_2026-10-28_preregistration.md``.

Every student gets the same inputs: the board, the ask kind, and each option's object (side, zone,
card types, P/T, tapped, token, or the option's word). They differ only in how they see the source
card, the card whose ability asks:
- ``none``: nothing (the floor);
- ``name``: its oracle id, as an embedding (today's policy reads names). Unk-dropout 0.1 lets it
  learn a fallback for cards it never saw;
- ``components``: the bag of its IR tokens, tools/k1 ``card_inputs`` (K1c's best card encoder).

The split holds out 20% of source cards. The metric is top-1 accuracy: a pick is correct when it is
one of the options of highest probe value.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import torch
from torch import nn

_K1 = importlib.util.spec_from_file_location(
    "k1_train", Path(__file__).resolve().parents[1] / "k1" / "train.py")
assert _K1 is not None and _K1.loader is not None
K1 = importlib.util.module_from_spec(_K1)
_K1.loader.exec_module(K1)  # puts MTG_REPO on sys.path, as tools/k1 does

from MTG_bot.utils import rng

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M15", "ORI", "M19",
        "DOM", "WAR", "ELD", "THB", "IKO", "FDN")
KINDS = ("target", "sacrifice", "discard", "may", "choose", "one_of")
ZONES = ("battlefield", "graveyard", "hand", "exile", "library", "other")
WORDS = ("fire", "skip", "DONE", "0", "1", "2", "3", "top", "bottom")
TYPES = ("Creature", "Land", "Artifact", "Enchantment", "Planeswalker", "Instant", "Sorcery")
MAX_OPTIONS = 16  # larger target menus are rare; dropped rather than truncated (counted in report)
ENCODERS = ("none", "name", "components")
COL = {c: i for i, c in enumerate(f"{s}.{f}" for s in ("me", "opp") for f in (
    "life", "hand", "library", "graveyard", "exile", "creatures", "power", "toughness",
    "tokens", "counters", "tapped", "lands"))}


def value(b: list[int]) -> float:
    """The probe's value of a board from the asking seat (pre-registered; not a strength claim)."""
    def d(field: str) -> float:
        return b[COL[f"me.{field}"]] - b[COL[f"opp.{field}"]]
    return (d("life") + 0.5 * (d("power") + d("toughness")) + 1.5 * d("creatures") + d("hand")
            + d("lands") - 0.5 * d("tapped"))


def _h(text: str) -> float:
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) / 0x1_0000_0000


def option_features(f: dict[str, Any]) -> list[float]:
    out = [float("oid" in f), float(bool(f.get("player"))), float("word" in f),
           float(f.get("mine") is True), float(f.get("mine") is False)]
    out += [float(f.get("zone") == z) for z in ZONES]
    types = f.get("types", "")
    out += [float(t in types) for t in TYPES]
    p, t = (f.get("pt") or [None, None])
    out += [float(p or 0) / 5, float(t or 0) / 5, float(bool(f.get("tapped"))),
            float(bool(f.get("token")))]
    out += [float(f.get("word") == w) for w in WORDS]
    return out


N_OPT = len(option_features({}))


def load(data: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows, dropped = [], defaultdict(int)
    for code in SETS:
        paths = sorted(data.glob(f"k2_{code}.jsonl")) + sorted(data.glob(f"k2_{code}_*.jsonl"))
        if not paths:
            dropped["missing set"] += 1
            continue
        for line in (line for path in paths for line in path.open(encoding="utf-8")):
            r = json.loads(line)
            if r.get("kind") == "manifest":
                continue
            if r["source"] is None:
                dropped["no source card"] += 1
                continue
            if len(r["options"]) > MAX_OPTIONS:
                dropped[f"more than {MAX_OPTIONS} options"] += 1
                continue
            v = [value(a) - value(r["before"]) for a in r["after"]]
            if max(v) - min(v) <= 0.01:
                dropped["uninformative"] += 1
                continue
            r["best"] = [i for i, x in enumerate(v) if x >= max(v) - 0.01]
            r["values"] = v
            rows.append(r)
    return rows, dict(dropped)


class Chooser(nn.Module):
    def __init__(self, encoder: str, n_names: int, n_ir: int, d: int = 64) -> None:
        super().__init__()
        self.encoder = encoder
        self.state = nn.Sequential(nn.Linear(24, d), nn.ReLU())
        self.kind = nn.Embedding(len(KINDS), d)
        if encoder == "name":
            self.src = nn.Embedding(n_names + 1, d)
        elif encoder == "components":
            self.src = nn.Sequential(nn.Linear(n_ir, d), nn.ReLU(), nn.Linear(d, d))
        self.opt = nn.Sequential(nn.Linear(N_OPT, d), nn.ReLU())
        self.head = nn.Sequential(nn.Linear(3 * d, d), nn.ReLU(), nn.Linear(d, 1))

    def forward(self, state, kind, src, opts, mask):
        h = self.state(state) + self.kind(kind)
        if self.encoder != "none":
            h = h + self.src(src)
        o = self.opt(opts)
        h = h.unsqueeze(1).expand(-1, o.shape[1], -1)
        score = self.head(torch.cat([h, o, h * o], dim=-1)).squeeze(-1)
        return score.masked_fill(~mask, float("-inf"))


def tensors(rows: list[dict[str, Any]], names: dict[str, int], ir: dict[str, torch.Tensor],
            n_ir: int, stats: dict[str, torch.Tensor], unk_drop: float = 0.0,
            stream: Any = None):
    b = len(rows)
    state = (torch.tensor([r["before"] for r in rows], dtype=torch.float32) - stats["mean"]) / stats["std"]
    kind = torch.tensor([KINDS.index(r["kind"]) for r in rows])
    name = torch.tensor([0 if (unk_drop and stream.random() < unk_drop) else names.get(r["source"], 0)
                         for r in rows])
    bag = torch.stack([ir.get(r["source"], torch.zeros(n_ir)) for r in rows])
    opts = torch.zeros(b, MAX_OPTIONS, N_OPT)
    mask = torch.zeros(b, MAX_OPTIONS, dtype=torch.bool)
    target = torch.zeros(b, MAX_OPTIONS)
    for i, r in enumerate(rows):
        for j, f in enumerate(r["facts"]):
            opts[i, j] = torch.tensor(option_features(f))
            mask[i, j] = True
        for j in r["best"]:
            target[i, j] = 1.0 / len(r["best"])
    return state, kind, name, bag, opts, mask, target


def fit_predict(encoder: str, train: list, val: list, tests: list[list], names: dict, ir: dict,
                n_ir: int, stats: dict, epochs: int, seed: int) -> list[torch.Tensor]:
    """Train one chooser and return its picks on each test slice."""
    rng.seed_all(seed, seed_frameworks=True)
    model = Chooser(encoder, len(names), n_ir)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    order = rng.substream("bench", "k2", encoder, seed)
    best, best_state, bad = float("inf"), None, 0

    def run(rows: list, drop: float = 0.0):
        state, kind, name, bag, opts, mask, target = tensors(rows, names, ir, n_ir, stats, drop, order)
        src = name if encoder == "name" else bag
        return model(state, kind, src, opts, mask), target

    for _epoch in range(epochs):
        model.train()
        idx = list(range(len(train)))
        order.shuffle(idx)
        for start in range(0, len(idx), 128):
            scores, target = run([train[i] for i in idx[start:start + 128]],
                                 0.1 if encoder == "name" else 0.0)
            loss = -(target * torch.log_softmax(scores, dim=-1).nan_to_num(neginf=0.0)).sum(-1).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            scores, target = run(val)
            vloss = -(target * torch.log_softmax(scores, -1).nan_to_num(neginf=0.0)).sum(-1).mean().item()
        if vloss < best - 1e-4:
            best, best_state, bad = vloss, {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 4:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    picks = []
    with torch.no_grad():
        for test in tests:
            scores, _ = run(test)
            picks.append(scores.argmax(-1))
    return picks


def correct(picks: torch.Tensor, rows: list) -> dict[str, list[float]]:
    """Per source card, 1.0 / 0.0 per decision: was the pick among the best options?"""
    by_card: dict[str, list[float]] = defaultdict(list)
    for p, r in zip(picks.tolist(), rows, strict=True):
        by_card[r["source"]].append(float(p in r["best"]))
    return by_card


def mean_acc(by_card: dict[str, list[float]], cards: list[str]) -> float:
    flat = [x for c in cards for x in by_card[c]]
    return sum(flat) / len(flat) if flat else float("nan")


def paired(a: dict, b: dict, key: str, draws: int = 1000) -> dict[str, Any]:
    cards = sorted(set(a) & set(b))
    stream = rng.substream("bench", "k2-paired", key)
    gaps = []
    for _ in range(draws):
        pick = [cards[stream.randrange(len(cards))] for _ in cards]
        gaps.append(mean_acc(a, pick) - mean_acc(b, pick))
    gaps.sort()
    return {"cards": len(cards), "gap": round(mean_acc(a, cards) - mean_acc(b, cards), 4),
            "ci95": [round(gaps[int(0.025 * draws)], 4), round(gaps[int(0.975 * draws) - 1], 4)]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    torch.set_num_threads(args.threads)
    started = time.perf_counter()
    rows, dropped = load(Path(args.data))
    inputs: dict = {}
    for code in SETS:
        for key, val in K1.card_inputs(code).items():
            inputs.setdefault(key, val)
    sources = sorted({r["source"] for r in rows})
    held = {s for s in sources if _h(f"k2:{s}") < 0.2}
    seen_test = [r for r in rows if r["source"] not in held and _h(f"k2t:{r['set']}:{r['seed']}:{r['pos']}") < 0.1]
    seen_ids = {id(r) for r in seen_test}
    pool = [r for r in rows if r["source"] not in held and id(r) not in seen_ids]
    val_cards = {r["source"] for r in pool if _h(f"k2v:{r['source']}") < 0.1}
    val = [r for r in pool if r["source"] in val_cards]
    train = [r for r in pool if r["source"] not in val_cards]
    held_test = [r for r in rows if r["source"] in held]
    names = {s: i + 1 for i, s in enumerate(sorted({r["source"] for r in train}))}
    vocab: dict[str, int] = {}
    for s in {r["source"] for r in train}:
        for t in inputs.get((s, "card"), {}).get("ir", ()):
            vocab.setdefault(t, len(vocab))
    ir = {}
    for s in sources:
        bag = torch.zeros(len(vocab))
        for t in inputs.get((s, "card"), {}).get("ir", ()):
            if t in vocab:
                bag[vocab[t]] += 1.0
        ir[s] = torch.log1p(bag)
    before = torch.tensor([r["before"] for r in train], dtype=torch.float32)
    stats = {"mean": before.mean(0), "std": before.std(0).clamp(min=1e-3)}
    report: dict[str, Any] = {
        "decisions": {"train": len(train), "val": len(val), "seen_test": len(seen_test),
                      "heldout_test": len(held_test)},
        "source_cards": {"train": len(names), "heldout": len({r["source"] for r in held_test})},
        "dropped": dropped,
        "chance": {name: round(statistics.mean(len(r["best"]) / len(r["options"]) for r in part), 4)
                   for name, part in (("seen", seen_test), ("heldout", held_test)) if part},
        "results": {},
    }
    per: dict[str, dict[str, dict]] = {}
    for encoder in ENCODERS:
        t0 = time.perf_counter()
        per[encoder] = {}
        parts = (("seen", seen_test), ("heldout", held_test))
        all_picks = fit_predict(encoder, train, val, [part for _, part in parts], names, ir,
                                len(vocab), stats, args.epochs, seed=20261028)
        for (name, part), picks in zip(parts, all_picks, strict=True):
            per[encoder][name] = correct(picks, part)
            cards = sorted(per[encoder][name])
            report["results"].setdefault(name, {})[encoder] = round(mean_acc(per[encoder][name], cards), 4)
            for kind in ("target", "may"):
                sub = [r for r in part if r["kind"] == kind]
                if sub:
                    acc = sum(p in r["best"] for p, r in zip(picks.tolist(), part, strict=True)
                              if r["kind"] == kind) / len(sub)
                    report["results"].setdefault(f"{name}/{kind}", {})[encoder] = round(acc, 4)
        report[f"{encoder}_seconds"] = round(time.perf_counter() - t0, 1)
        print(json.dumps({encoder: {k: v.get(encoder) for k, v in report["results"].items()}}), flush=True)
    report["paired"] = {
        f"{split}: {a} - {b}": paired(per[a][split], per[b][split], f"{split}:{a}-{b}")
        for split in ("seen", "heldout")
        for a, b in (("name", "none"), ("components", "none"), ("components", "name"))
    }
    report["seconds"] = round(time.perf_counter() - started, 1)
    Path(args.out).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report["paired"], indent=1))
    print(f"done in {report['seconds']} s -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
