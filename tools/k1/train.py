"""Kill test K1, models: does a learned card encoder predict what unseen cards do?

    .venv/bin/python tools/k1/train.py --data DIR [--epochs 12] [--out FILE.json]
    MTG_REPO=/path/to/worktree ...   # compile cards with that tree (must match the data's tree)

Task. Predict the 24-number board change of one cast or activation from the board before it plus
a representation of the card. The rows come from tools/k1/gen.py.

Encoders, all at the same budget:
- **state**: no card input. The floor: what the board alone explains.
- **name**: one learned embedding per oracle id. An unseen card is `<unk>`, which is how the live
  policy reads cards today (REVIEW A-1).
- **ir-bag**: counts of the card's compiled-IR tokens (node tags, enum values, roles, numbers in
  buckets).
- **ir-seq**: the same tokens in tree order, through a small transformer. This tests composition,
  not just presence.
- **text-bag**: word counts of the Oracle text, self-name masked. No pretraining.
- **hybrid**: ir-bag and text-bag together.

Splits (docs/REVIEW_ARCHITECTURE_2026-10-27.md §4):
- **random**: rows of seen cards, 80/20.
- **cards**: 20% of M21 cards held out whole.
- **compound**: held-out cards whose atom PAIRS are rare in training, while every single atom of
  theirs still occurs in training. The CFQ idea, maximum compound divergence, made greedy.
- **M20** and **ZNR**: train on all of M21, test on the other set's cards that M21 does not
  contain.

Metric: R² of the normalized change on test rows against the training mean, reported as
[all 24 lanes, effect lanes]. The effect lanes are the ones a card's own entry cannot explain: the
opponent's side and my life, library, graveyard, exile, tokens and counters. There are two
references:
- **ceiling:** the per-card mean on the test rows themselves, what card identity alone could
  explain;
- **memorized:** the per-card mean on the training rows; seen cards only.

Every encoder gets the same printed-face tokens (types, P/T, mana value, colours), so none is
rigged. Every random choice goes through MTG_bot.utils.rng.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(os.environ.get("MTG_REPO", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audit"))

import torch
from torch import nn

from MTG_bot.core.ability_tree import ActivatedAbility, to_dict
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.errors import StateCorruptionError
from MTG_bot.utils import rng

MAX_SEQ = 256
ENCODERS = ("state", "name", "ir-bag", "ir-pairs", "ir-seq", "text-bag", "hybrid")


# --------------------------------------------------------------------------- card inputs


def _bucket(value: Any) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "num:?"
    return f"num:{n}" if 0 <= n <= 5 else ("num:6+" if n > 5 else "num:neg")


def ir_tokens(node: Any) -> list[str]:
    """Pre-order tokens of a to_dict tree: tags, enum values, roles, strings, bucketed numbers."""
    out: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            tag = value.get("tag")
            if "name" in value and len(value) == 2 and tag:
                out.append(f"{tag}.{value['name']}")  # an enum
                return
            if tag == "QConst":
                out.append(_bucket(value.get("value")))
                return
            if tag:
                out.append(tag)
            for key, child in value.items():
                if key == "tag" or child in (None, [], {}, ""):
                    continue
                if key == "pairs":
                    for role, item in child:
                        out.append(f"role:{role}")
                        visit(item)
                    continue
                if key in ("name", "oracle_id", "type_line"):
                    continue  # identity, not rules: a card's own name must not leak in
                out.append(f"@{key}")
                visit(child)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, bool):
            out.append(f"bool:{value}")
        elif isinstance(value, int):
            out.append(_bucket(value))
        elif isinstance(value, str):
            out.append(f"str:{value}")

    visit(node)
    return out


def ir_pairs(node: Any) -> list[str]:
    """Parent>child token bigrams of the same tree (``role:target>Selector``,
    ``FAtomPred.TYPE_EQ>str:Creature``): which atom applies to what, without a sequence model."""
    out: list[str] = []

    def label(value: Any) -> str | None:
        if isinstance(value, dict):
            tag = value.get("tag")
            if "name" in value and len(value) == 2 and tag:
                return f"{tag}.{value['name']}"
            if tag == "QConst":
                return _bucket(value.get("value"))
            return tag
        if isinstance(value, bool):
            return f"bool:{value}"
        if isinstance(value, int):
            return _bucket(value)
        if isinstance(value, str):
            return f"str:{value}"
        return None

    def visit(value: Any, parent: str | None) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item, parent)
            return
        here = label(value)
        if here is not None and parent is not None:
            out.append(f"{parent}>{here}")
        if not isinstance(value, dict) or ("name" in value and len(value) == 2) \
                or value.get("tag") == "QConst":
            return
        for key, child in value.items():
            if key == "tag" or child in (None, [], {}, "") or key in ("name", "oracle_id", "type_line"):
                continue
            if key == "pairs":
                for role, item in child:
                    out.append(f"{here}>role:{role}")
                    visit(item, f"role:{role}")
                continue
            visit(child, here)

    visit(node, None)
    return out


def text_tokens(raw: Any) -> list[str]:
    text = " ".join(raw.sentences).lower()
    for name in sorted({raw.identity.name, raw.identity.name.split(",")[0]}, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(name.lower())}(?!\w)", " ~ ", text)
    words = re.findall(r"[a-z~]+|\d+|[{}+/\-]", text)
    return [_bucket(w) if w.isdigit() else w for w in words]


def face_tokens(raw: Any) -> list[str]:
    return ([f"type:{t}" for t in raw.types] + [f"sub:{t}" for t in raw.subtypes]
            + [f"color:{c}" for c in raw.colors] + [f"mv:{_bucket(raw.mana_value)}"]
            + [f"p:{_bucket(raw.power_raw)}", f"t:{_bucket(raw.toughness_raw)}"])


def card_inputs(set_code: str) -> dict[tuple[str, str], dict[str, Any]]:
    """(oid, unit) -> {ir, text} for every card of the set the compiler builds."""
    registry = build_full_registry()
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for oid, raw in ingest_pool(REPO / "MTG_bot" / "data" / f"{set_code}.json").items():
        try:
            result = compile_card(raw, registry)
            card = result.card
        except StateCorruptionError:
            continue
        except Exception:  # noqa: BLE001, S112 - a compile crash is a gap, not a row
            continue
        # The printed face (types, P/T, mana value, colours) goes to EVERY card encoder alike:
        # a cast creature's own entry is most of its board change, and the name embedding learns
        # it for free, so withholding it from the IR/text encoders would rig the comparison.
        face = face_tokens(raw)
        text = face + text_tokens(raw)
        whole = face + ir_tokens({"abilities": [to_dict(a) for a in card.abilities],
                                  "keywords": [to_dict(k) for k in card.keywords]})
        tree = {"abilities": [to_dict(a) for a in card.abilities],
                "keywords": [to_dict(k) for k in card.keywords]}
        # "full": nothing unparsed or ambiguous, so the printed text says only what the engine does
        # (the supply's "compiled" test, games.py). Castable pools also deal partly blank cards.
        full = not (result.unparsed or result.ambiguities or result.back_face_unparsed)
        out[(oid, "card")] = {"ir": whole, "text": text, "pairs": face + ir_pairs(tree),
                              "full": full}
        for i, ability in enumerate(card.abilities):
            if isinstance(ability, ActivatedAbility):
                out[(oid, f"ability:{i}")] = {"ir": ir_tokens(to_dict(ability)), "text": text,
                                              "pairs": ir_pairs(to_dict(ability))}
    return out


# --------------------------------------------------------------------------- data


def load(data_dir: Path, set_code: str) -> list[dict[str, Any]]:
    path = data_dir / f"k1_{set_code}.jsonl"
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row.get("kind") != "manifest":
                rows.append(row)
    return rows


def _h(text: str) -> float:
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) / 0x1_0000_0000


def atoms_of_tokens(tokens: list[str]) -> set[str]:
    """Atom-level units of a card for the compound split: verb, predicate, keyword and node tags."""
    return {t for t in tokens if t.startswith(("Verb.", "FAtomPred.", "Keyword.", "SelectorMode."))
            or (t[:1].isupper() and "." not in t)}


def compound_split(cards: list[str], tokens: dict[str, list[str]], share: float = 0.2) -> set[str]:
    """Held-out cards whose atom pairs are rare, keeping every single atom seen in training."""
    atoms = {c: atoms_of_tokens(tokens[c]) for c in cards}
    pair_count: Counter = Counter()
    for c in cards:
        for a in atoms[c]:
            for b in atoms[c]:
                if a < b:
                    pair_count[(a, b)] += 1

    def rarity(c: str) -> float:
        pairs = [(a, b) for a in atoms[c] for b in atoms[c] if a < b]
        return sum(1 for p in pairs if pair_count[p] <= 2) / max(1, len(pairs))

    test: set[str] = set()
    target = int(share * len(cards))
    for c in sorted(cards, key=lambda c: (-rarity(c), _h(c))):
        if len(test) >= target:
            break
        trial = test | {c}
        seen = set().union(*(atoms[x] for x in cards if x not in trial))
        if atoms[c] <= seen:
            test = trial
    return test


def split_rows(rows: list[dict[str, Any]], how: str, tokens: dict[str, list[str]],
               salt: str = "card") -> tuple[list, list]:
    cards = sorted({r["oid"] for r in rows})
    if how == "random":
        test = [r for r in rows if _h(f"row:{r['seed']}:{r['oid']}:{r['turn']}:{r['pre']}") < 0.2]
        ids = {id(r) for r in test}
        return [r for r in rows if id(r) not in ids], test
    if how == "cards":
        held = {c for c in cards if _h(f"{salt}:{c}") < 0.2}
    else:
        held = compound_split(cards, {c: tokens.get(c, []) for c in cards})
    return [r for r in rows if r["oid"] not in held], [r for r in rows if r["oid"] in held]


# --------------------------------------------------------------------------- models


class Model(nn.Module):
    def __init__(self, encoder: str, n_state: int, n_out: int, sizes: dict[str, int]) -> None:
        super().__init__()
        self.encoder = encoder
        width = 0
        if encoder == "name":
            self.names = nn.Embedding(sizes["names"], 64)
            width = 64
        if encoder in ("ir-bag", "hybrid"):
            self.ir = nn.Linear(sizes["ir"], 128)
            width += 128
        if encoder in ("text-bag", "hybrid"):
            self.text = nn.Linear(sizes["text"], 128)
            width += 128
        if encoder == "ir-pairs":
            self.ir = nn.Linear(sizes["ir"], 128)
            self.pairs = nn.Linear(sizes["pairs"], 128)
            width += 256
        if encoder == "ir-seq":
            self.embed = nn.Embedding(sizes["ir"] + 1, 64, padding_idx=0)
            layer = nn.TransformerEncoderLayer(64, 4, 128, dropout=0.1, batch_first=True)
            self.seq = nn.TransformerEncoder(layer, 2)
            width = 64
        self.head = nn.Sequential(nn.Linear(width + n_state, 256), nn.ReLU(),
                                  nn.Linear(256, 256), nn.ReLU(), nn.Linear(256, n_out))

    def forward(self, state: torch.Tensor, card: dict[str, torch.Tensor]) -> torch.Tensor:
        parts = []
        if self.encoder == "name":
            parts.append(self.names(card["name"]))
        if self.encoder in ("ir-bag", "hybrid"):
            parts.append(torch.relu(self.ir(card["ir_bag"])))
        if self.encoder in ("text-bag", "hybrid"):
            parts.append(torch.relu(self.text(card["text_bag"])))
        if self.encoder == "ir-pairs":
            parts.append(torch.relu(self.ir(card["ir_bag"])))
            parts.append(torch.relu(self.pairs(card["pairs_bag"])))
        if self.encoder == "ir-seq":
            ids = card["ir_seq_unique"]  # one row per distinct card in the batch
            mask = ids == 0
            hidden = self.seq(self.embed(ids), src_key_padding_mask=mask)
            keep = (~mask).unsqueeze(-1).float()
            pooled = (hidden * keep).sum(1) / keep.sum(1).clamp(min=1)
            parts.append(pooled[card["ir_seq_index"]])
        parts.append(state)
        return self.head(torch.cat(parts, dim=-1))


class CardTable:
    """Every card's inputs built once per split: bags, token sequence, name id, by row index."""

    def __init__(self, inputs: dict, vocab: dict) -> None:
        self.keys = sorted(inputs)
        self.index = {k: i + 1 for i, k in enumerate(self.keys)}  # 0 = card not compiled
        n = len(self.keys) + 1
        self.ir_bag = torch.zeros(n, len(vocab["ir"]))
        self.text_bag = torch.zeros(n, len(vocab["text"]))
        self.pairs_bag = torch.zeros(n, len(vocab.get("pairs", {})))
        self.seq = torch.zeros(n, MAX_SEQ, dtype=torch.long)
        self.name = torch.zeros(n, dtype=torch.long)
        for k, i in self.index.items():
            card = inputs[k]
            ids = [vocab["ir"][t] for t in card["ir"] if t in vocab["ir"]]
            for j in ids:
                self.ir_bag[i, j] += 1.0
            for t in card["text"]:
                if t in vocab["text"]:
                    self.text_bag[i, vocab["text"][t]] += 1.0
            for t in card.get("pairs", ()):
                if t in vocab.get("pairs", {}):
                    self.pairs_bag[i, vocab["pairs"][t]] += 1.0
            seq_ids = [j + 1 for j in ids[:MAX_SEQ]]
            if seq_ids:
                self.seq[i, : len(seq_ids)] = torch.tensor(seq_ids, dtype=torch.long)
            self.name[i] = vocab["names"].get(k[0], 0)
        self.ir_bag = torch.log1p(self.ir_bag)
        self.text_bag = torch.log1p(self.text_bag)
        self.pairs_bag = torch.log1p(self.pairs_bag)

    def row_index(self, row: dict) -> int:
        return self.index.get((row["oid"], row["unit"])) or self.index.get((row["oid"], "card"), 0)


def fit_predict(encoder: str, train: list, test: list, table: CardTable, vocab: dict,
                stats: dict, epochs: int, seed: int) -> torch.Tensor:
    rng.seed_all(seed, seed_frameworks=True)
    n_state = len(stats["s_mean"])
    model = Model(encoder, n_state, n_state, {"names": len(vocab["names"]) + 1,
                                              "ir": len(vocab["ir"]), "text": len(vocab["text"]),
                                              "pairs": len(vocab.get("pairs", {}))})
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    # early stopping on 10% of the TRAINING cards, held out whole (no row leakage)
    tr_cards = sorted({r["oid"] for r in train})
    val_cards = {c for c in tr_cards if _h(f"val:{c}") < 0.1} if encoder != "state" else set()
    fit = [r for r in train if r["oid"] not in val_cards]
    val = [r for r in train if r["oid"] in val_cards] or fit[: max(1, len(fit) // 10)]
    best, best_state, bad = math.inf, None, 0
    # ir-seq encodes each distinct card once per batch; big pools (K1b) use big batches throughout
    batch = 1024 if encoder == "ir-seq" or len(train) > 100_000 else 256
    order_rng = rng.substream("bench", "k1", encoder, seed)
    for _epoch in range(epochs):
        model.train()
        idx = list(range(len(fit)))
        order_rng.shuffle(idx)
        for start in range(0, len(idx), batch):
            rows = [fit[i] for i in idx[start:start + batch]]
            s, y, c = tensors(rows, table, stats)
            loss = ((model(s, c) - y) ** 2).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            s, y, c = tensors(val, table, stats)
            vloss = ((model(s, c) - y) ** 2).mean().item()
        if vloss < best - 1e-4:
            best, best_state, bad = vloss, {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 3:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    preds = []
    with torch.no_grad():
        for start in range(0, len(test), 1024):
            s, _y, c = tensors(test[start:start + 1024], table, stats)
            preds.append(model(s, c))
    return torch.cat(preds) if preds else torch.zeros(0, n_state)


def tensors(rows: list, table: CardTable, stats: dict):
    s = torch.tensor([r["pre"] for r in rows], dtype=torch.float32)
    y = torch.tensor([r["delta"] for r in rows], dtype=torch.float32)
    s = (s - stats["s_mean"]) / stats["s_std"]
    y = y / stats["y_std"]
    idx = torch.tensor([table.row_index(r) for r in rows], dtype=torch.long)
    unique, inverse = torch.unique(idx, return_inverse=True)
    return s, y, {
        "name": table.name[idx],
        "ir_bag": table.ir_bag[idx],
        "text_bag": table.text_bag[idx],
        "pairs_bag": table.pairs_bag[idx],
        "ir_seq_unique": table.seq[unique],
        "ir_seq_index": inverse,
    }


#: Lanes the card's own entry onto the battlefield cannot explain: the opponent's whole side, and
#: my life, library, graveyard, exile, tokens and counters. These carry the rules-text effects.
EFFECT_LANES = tuple(i for i, c in enumerate(
    f"{side}.{f}" for side in ("me", "opp") for f in (
        "life", "hand", "library", "graveyard", "exile", "creatures", "power", "toughness",
        "tokens", "counters", "tapped", "lands"))
    if c.startswith("opp.") or c in ("me.life", "me.library", "me.graveyard", "me.exile",
                                      "me.tokens", "me.counters"))


def r2(pred: torch.Tensor, y: torch.Tensor, mean: torch.Tensor,
       lanes: tuple[int, ...] | None = None) -> float:
    if lanes is not None:
        pred, y, mean = pred[:, lanes], y[:, lanes], mean[list(lanes)]
    sse = ((pred - y) ** 2).sum().item()
    sst = ((y - mean) ** 2).sum().item()
    return round(1 - sse / sst, 4) if sst else float("nan")


def card_bootstrap(pred: torch.Tensor, y: torch.Tensor, mean: torch.Tensor, test: list,
                   draws: int = 200) -> list[float]:
    """95% interval of effect-lane R² resampling TEST CARDS (the unit that varies), seeded."""
    by_card: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(test):
        by_card[r["oid"]].append(i)
    cards = sorted(by_card)
    stream = rng.substream("bench", "k1-bootstrap", len(test))
    values = []
    for _ in range(draws):
        idx = [i for _ in cards for i in by_card[cards[stream.randrange(len(cards))]]]
        values.append(r2(pred[idx], y[idx], mean, EFFECT_LANES))
    values.sort()
    return [values[int(0.025 * draws)], values[int(0.975 * draws) - 1]]


def evaluate(split: str, train: list, test: list, inputs: dict, epochs: int,
             encoders: tuple[str, ...] = ENCODERS) -> dict[str, Any]:
    vocab = {
        "names": {c: i + 1 for i, c in enumerate(sorted({r["oid"] for r in train}))},
        "ir": {}, "text": {}, "pairs": {},
    }
    for r in train:
        card = inputs.get((r["oid"], r["unit"])) or inputs.get((r["oid"], "card"))
        if card is None:
            continue
        for t in card["ir"]:
            vocab["ir"].setdefault(t, len(vocab["ir"]))
        for t in card["text"]:
            vocab["text"].setdefault(t, len(vocab["text"]))
        for t in card.get("pairs", ()):
            vocab["pairs"].setdefault(t, len(vocab["pairs"]))
    pre = torch.tensor([r["pre"] for r in train], dtype=torch.float32)
    dlt = torch.tensor([r["delta"] for r in train], dtype=torch.float32)
    stats = {"s_mean": pre.mean(0), "s_std": pre.std(0).clamp(min=1e-3),
             "y_std": dlt.std(0).clamp(min=1e-3)}
    table = CardTable(inputs, vocab)
    y_test = torch.tensor([r["delta"] for r in test], dtype=torch.float32) / stats["y_std"]
    y_mean = (dlt / stats["y_std"]).mean(0)
    # reference ceiling: the per-card mean change ON THE TEST ROWS (card identity alone)
    by_card: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(test):
        by_card[r["oid"]].append(i)
    oracle = torch.zeros_like(y_test)
    for idx in by_card.values():
        oracle[idx] = y_test[idx].mean(0)
    # memorization baseline: each test card's mean change on the TRAIN rows (seen cards only)
    train_means: dict[str, torch.Tensor] = {}
    by_train: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(train):
        by_train[r["oid"]].append(i)
    y_train = dlt / stats["y_std"]
    for oid, idx in by_train.items():
        train_means[oid] = y_train[idx].mean(0)
    memo = torch.stack([train_means.get(r["oid"], y_mean) for r in test]) if test else oracle
    result: dict[str, Any] = {
        "train_rows": len(train), "test_rows": len(test),
        "train_cards": len({r["oid"] for r in train}), "test_cards": len(by_card),
        "ceiling_card_mean_from_test": [r2(oracle, y_test, y_mean),
                                        r2(oracle, y_test, y_mean, EFFECT_LANES)],
        "memorized_card_mean_from_train": [r2(memo, y_test, y_mean),
                                           r2(memo, y_test, y_mean, EFFECT_LANES)],
    }
    for encoder in encoders:
        started = time.perf_counter()
        pred = fit_predict(encoder, train, test, table, vocab, stats, epochs, seed=20261027)
        result[encoder] = [r2(pred, y_test, y_mean), r2(pred, y_test, y_mean, EFFECT_LANES)]
        if split != "random":
            result[f"{encoder}_ci95"] = card_bootstrap(pred, y_test, y_mean, test)
        result[f"{encoder}_seconds"] = round(time.perf_counter() - started, 1)
    unseen = [t for r in test for t in (inputs.get((r["oid"], "card")) or {}).get("ir", [])
              if t not in vocab["ir"]]
    result["test_ir_tokens_unseen_in_train"] = len(set(unseen))
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0, help="cap rows per set (smoke runs)")
    ap.add_argument("--splits", default="random,cards,compound,M20,ZNR")
    ap.add_argument("--encoders", default=",".join(ENCODERS))
    ap.add_argument("--card-salt", default="card", help="hash salt of the held-out-cards split")
    ap.add_argument("--partial", help="append each finished split here as one JSON line")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    torch.set_num_threads(min(16, os.cpu_count() or 4))
    data = Path(args.data)
    inputs = {**card_inputs("M21"), **card_inputs("M20"), **card_inputs("ZNR")}
    m21 = load(data, "M21")
    if args.limit:
        m21 = m21[: args.limit]
    m21_cards = {r["oid"] for r in m21}
    tokens = {oid: inp["ir"] for (oid, unit), inp in inputs.items() if unit == "card"}
    report: dict[str, Any] = {"repo": str(REPO), "epochs": args.epochs, "splits": {}}
    for split in args.splits.split(","):
        if split in ("random", "cards", "compound"):
            train, test = split_rows(m21, split, tokens, args.card_salt)
        else:
            other = load(data, split)
            if args.limit:
                other = other[: args.limit]
            train, test = m21, [r for r in other if r["oid"] not in m21_cards]
        if split == "compound":
            tr_pairs = set()
            for c in {r["oid"] for r in train}:
                a = sorted(atoms_of_tokens(tokens.get(c, [])))
                tr_pairs.update((x, y) for i, x in enumerate(a) for y in a[i + 1:])
            te_pairs = set()
            for c in {r["oid"] for r in test}:
                a = sorted(atoms_of_tokens(tokens.get(c, [])))
                te_pairs.update((x, y) for i, x in enumerate(a) for y in a[i + 1:])
            report["compound_test_pairs_unseen_in_train"] = round(
                len(te_pairs - tr_pairs) / max(1, len(te_pairs)), 3)
        print(f"[{split}] train {len(train)} rows / test {len(test)} rows", flush=True)
        report["splits"][split] = evaluate(split, train, test, inputs, args.epochs,
                                           tuple(args.encoders.split(",")))
        if args.partial:
            with open(args.partial, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"split": split, "card_salt": args.card_salt,
                                     "encoders": args.encoders, **report["splits"][split]}) + "\n")
        print(json.dumps({split: report["splits"][split]}), flush=True)
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
