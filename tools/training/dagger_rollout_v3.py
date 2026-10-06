"""Batch-3 filtered-DAgger rollout: replay every TRAINING pack with a
checkpoint answering its OWN scripted (pool-lane) decision points; the
scripted gold is recorded as the teacher label ONLY where it is still legal
in the state the model itself reached (engine legality = the vanilla pool
lane's own membership law, ``word in vocab`` — quantity.py). Gold that went
illegal after a divergence is skipped and COUNTED, never fabricated.

The recording path is the batch-2 recorder machinery itself: importing
``packrec_v2`` installs the v2 obs hook + choose digest stash; this module
replaces ``ExecCtx.take_decision`` with a wrapper that, at a scripted point,
encodes the v2 stream EXACTLY as ``encode_episode_v2``/``eval_rows`` do
(same vocab map, same ASK/SEP layout, same candidate span + ref law, same
BOS+tail truncation as ``ab_duel.BcAsk``), answers with the pointer argmax,
consumes the scripted pool word, and mirrors the ask log the vanilla pool
lane would have written. Every other ask goes untouched through the
v2-recorder → provider lanes.

Output episode file (``--out``): the ORIGINAL 96 ``episodes_v2.jsonl``
lines verbatim, then one dagger episode per pack that produced at least one
teacher label, tagged ``"source": "dagger"``. ``join_corpus`` must NEVER
see this file (pack names repeat; the eval split always comes from the
binding v2 file — pinned in test_bc_v3.py).

Run::

    .venv/bin/python -m tools.training.dagger_rollout_v3 \
        --ckpt tools/training/bc3_B_best.pt \
        --out tools/training/episodes_dagger.jsonl \
        --stats tools/training/bc3_rollout_base.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import torch

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from MTG_bot.core.executor.games import get_supply
from MTG_bot.core.executor.quantity import ExecCtx
from tools.audit import puzzle_cert as pcert
from tools.training import (
    bc_data_v2,
    packrec,
    packrec_v2,  # installs hooks + stash
)
from tools.training.bc_model import PointerBC

EPISODES_V2 = REPO / "tools" / "training" / "episodes_v2.jsonl"
PACKS_DIR = REPO / "tools" / "scenarios"

#: per-pack rollout state, reset by rollout_pack(); None disables the hook
_ST: dict[str, Any] | None = None


def _forward_idx(
    model: PointerBC,
    vocab: dict[str, int],
    rows: list[dict[str, Any]],
    current: dict[str, Any],
    max_len: int,
    device: torch.device,
) -> tuple[int, bool]:
    """Pointer argmax for ``current`` (a provisional gold-shaped row) on the
    stream of the preceding recorded rows. Encoding is encode_episode_v2
    byte-exact; truncation mirrors BcAsk (keep BOS + the last window)."""
    ep = bc_data_v2.encode_episode_v2(
        {
            "pack": "x",
            "card": "x",
            "asks": [{**r, "gold": False, "gold_idx": 0} for r in rows] + [current],
        },
        vocab,
    )
    gold = ep["gold"][0]
    seq, pos = ep["seq"], gold["pos"]
    trunc = len(seq) > max_len
    if trunc:
        kept = [seq[0], *seq[-(max_len - 1) :]]
        pos = len(kept) - (len(seq) - pos)
        seq = kept
    n_c = len(gold["cand_ids"])
    l_max = max(len(s) for s in gold["cand_ids"])
    cand_ids = torch.zeros(1, n_c, l_max, dtype=torch.long)
    cand_mask = torch.zeros(1, n_c, l_max, dtype=torch.bool)
    for ci, ids in enumerate(gold["cand_ids"]):
        cand_ids[0, ci, : len(ids)] = torch.tensor(ids, dtype=torch.long)
        cand_mask[0, ci, : len(ids)] = True
    is_pass = torch.tensor([[c == "PASS" for c in current["candidates"]]])
    tokens = torch.tensor([seq], dtype=torch.long)
    with torch.no_grad():
        out = model.forward(
            tokens.to(device),
            torch.zeros_like(tokens, dtype=torch.bool, device=device),
            torch.zeros(1, dtype=torch.long, device=device),
            torch.tensor([pos], dtype=torch.long, device=device),
            cand_ids.to(device),
            cand_mask.to(device),
            is_pass.to(device),
        )
    return int(out.argmax(-1)[0]), trunc


def _take_dagger(self: ExecCtx, vocab: tuple, what: str) -> str:
    st = _ST
    if st is None or packrec._records is None:
        return packrec_v2._take_recorded_v2(self, vocab, what)
    st["asks"] += 1
    cands = [str(v) for v in vocab]
    scripted = (
        self.decisions[self.decision_idx]
        if self.decision_idx < len(self.decisions)
        else None
    )
    if scripted is None or scripted not in vocab:
        # not this ask's scripted point; a stale pool head (gold went
        # illegal on the model's state) is the FILTERED skip, counted.
        if scripted is not None:
            st["illegal_skips"] += 1
        return packrec_v2._take_recorded_v2(self, vocab, what)
    st["points"] += 1
    obs = packrec._obs_snapshot(self)
    ground = bc_data_v2.ground_candidates(getattr(self, "world", None), what, cands)
    rows = list(packrec._records)
    current = {
        "ordinal": len(rows),
        "what": what,
        "candidates": cands,
        "obs": obs,
        "ground": ground,
        "gold": True,
        "gold_idx": 0,
    }
    pred, trunc = _forward_idx(
        st["model"], st["vocab"], rows, current, st["max_len"], st["device"]
    )
    if trunc:
        st["truncations"] += 1
    teacher = cands.index(str(scripted))
    ans_raw = vocab[pred]  # raw vocab TUPLE entry (vanilla lane returns raws)
    # consume the scripted word the vanilla pool lane would have eaten and
    # mirror ITS ask-log shape byte-exactly (quantity.py pool lane).
    self.decision_idx += 1
    if self.stream is not None:
        self.stream.ask_log.append((what, ans_raw))
    rows.append(
        {
            **current,
            "answer": str(ans_raw),
            "gold_idx": teacher,
            "dagger": {"model_idx": pred, "gold": str(scripted)},
        }
    )
    packrec._records.clear()
    packrec._records.extend(rows)
    st["applied"] += 1
    st["correct"] += int(pred == teacher)
    return ans_raw


ExecCtx.take_decision = _take_dagger  # type: ignore[method-assign]


def rollout_pack(
    path: Path,
    supply: Any,
    model: PointerBC,
    vocab: dict[str, int],
    max_len: int,
    device: torch.device,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """One pack -> (dagger episode or None, per-pack stats). The hook sees
    only THIS pack's asks; pcert._recorder stays None (no AskRec needed)."""
    global _ST
    _ST = {
        "model": model,
        "vocab": vocab,
        "max_len": max_len,
        "device": device,
        "asks": 0,
        "points": 0,
        "applied": 0,
        "correct": 0,
        "illegal_skips": 0,
        "truncations": 0,
    }
    pack = json.loads(path.read_text(encoding="utf-8"))
    if not any(s.get("decisions") for s in pack.get("steps", ())):
        _ST = None
        return None, {**_STATS_SEED}
    packrec._records = []
    try:
        _runner, ok = pcert._drive(pack, supply)
    except Exception as exc:  # noqa: BLE001 - a broken rollout is data, counted
        _runner, ok = None, False
        print(f"  {path.name}: rollout raised {type(exc).__name__}: {exc}")
    finally:
        rows, _ST_prev, _ST = packrec._records, _ST, None
        packrec._records = None
    st = _ST_prev
    st["rollout_ok"] = int(ok is True)
    if st["applied"] == 0:
        return None, st
    for r in rows:
        r["gold"] = "dagger" in r
    card = next(
        (
            c.get("real") or c.get("name")
            for c in pack.get("cards", [])
            if c.get("real") or c.get("name")
        ),
        path.stem,
    )
    ep = {
        "pack": path.name,
        "card": card,
        "asks": rows,
        "gold_ordinals": [r["ordinal"] for r in rows if r["gold"]],
        "source": "dagger",
    }
    return ep, st


_STATS_SEED = {
    "asks": 0,
    "points": 0,
    "applied": 0,
    "correct": 0,
    "illegal_skips": 0,
    "truncations": 0,
    "rollout_ok": 0,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Batch-3 filtered-DAgger rollout.")
    ap.add_argument("--ckpt", type=Path, required=True)
    ap.add_argument("--dir", type=Path, default=PACKS_DIR)
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="mixed episode file (originals + dagger); omit for "
        "stats-only control rollouts",
    )
    ap.add_argument("--stats", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=0, help="first N packs only")
    ap.add_argument("--device", default="auto", choices=("auto", "cuda", "cpu"))
    args = ap.parse_args(argv)

    device = torch.device(
        "cuda"
        if args.device == "auto" and torch.cuda.is_available()
        else args.device
        if args.device != "auto"
        else "cpu"
    )
    blob = torch.load(args.ckpt, map_location=device, weights_only=False)
    if blob.get("schema") != "v2":
        raise SystemExit("rollout needs a v2-schema checkpoint (bc_data_v2 obs)")
    model = PointerBC(**blob["config"])
    model.load_state_dict(blob["state"])
    model.to(device).eval()
    for p in model.parameters():
        p.requires_grad_(False)
    vocab = blob["vocab"]

    planned = {
        json.loads(line)["pack"]: sum(
            1 for r in json.loads(line)["asks"] if r.get("gold")
        )
        for line in EPISODES_V2.read_text(encoding="utf-8").splitlines()
    }
    supply = get_supply("all")
    paths = sorted(p for p in args.dir.glob("*.json"))
    if args.limit:
        paths = paths[: args.limit]
    t0 = time.perf_counter()
    episodes, agg = [], dict(_STATS_SEED)
    agg.update({"packs": 0, "planned_gold_points": 0, "packs_with_labels": 0})
    for p in paths:
        ep, st = rollout_pack(p, supply, model, vocab, model.max_len, device)
        agg["packs"] += 1
        agg["planned_gold_points"] += planned.get(p.name, 0)
        for k in _STATS_SEED:
            agg[k] += st[k]
        if ep is not None:
            episodes.append(ep)
            agg["packs_with_labels"] += 1
        print(
            f"{p.name}: applied {st['applied']}/{planned.get(p.name, 0)} "
            f"skips {st['illegal_skips']} ok {st['rollout_ok']}"
        )
    doc = {
        "produced_by": "tools/training/dagger_rollout_v3.py",
        "date": time.strftime("%Y-%m-%d"),
        "ckpt": str(args.ckpt),
        "device": str(device),
        "wall_seconds": round(time.perf_counter() - t0, 1),
        "stats": agg,
        "teacher_filter_law": "scripted gold recorded iff still legal "
        "(word in vocab, the vanilla pool lane's own test); diverged "
        "illegality is skipped and counted in illegal_skips",
    }
    args.stats.parent.mkdir(parents=True, exist_ok=True)
    args.stats.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as fh:
            for line in EPISODES_V2.read_text(encoding="utf-8").splitlines():
                fh.write(line + "\n")
            for ep in episodes:
                fh.write(json.dumps(ep, sort_keys=True) + "\n")
        print(
            f"wrote {args.out}: {len(EPISODES_V2.read_text().splitlines())} "
            f"originals + {len(episodes)} dagger episodes"
        )
    print(json.dumps({"stats": agg, "stats_file": str(args.stats)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
