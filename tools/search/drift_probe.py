"""Encoding-drift probe — quantify tokenization mismatch between eras.

KNOWLEDGE/2026-10-13/75 suspect (ii): a bc9-era checkpoint fed LIVE obs by
``bc_data_v2.obs_groups_v2`` through its OWN vocab may be reading the
current engine through a hole in its vocab — every out-of-era word maps to
``<unk>`` (BcAsk law: ``vocab.get(w, unk)``). If the UNK rate of live
serialization >> the UNK rate of the TRAINING corpus rows, the era
regression has a concrete input-distribution smoking gun, independent of
any gold-prior argument.

Instrumentation is a per-instance wrapper around ``BcAsk._decide``
(:func:`instrument_bcask`) installed via ``champ_shadow.run_champ_game``'s
``agent_hook`` — eval code stays untouched. Each live ask re-scores the
row's encode-visible words (site + v2 obs, exactly what
``encode_episode_v2`` puts between ASK and SEP) against the checkpoint
vocab and counts ``<unk>`` landings plus the OOV strings themselves (the
strings hashing to UNK are the first tokens of their card rows — name/
keyword words the era never saw). Training-side: the SAME scoring over
historical ``episodes_v2.jsonl`` rows (the git version the checkpoint was
trained on) under the same vocab.

Run::

    .venv/bin/python tools/search/drift_probe.py \
        --seeds 91,92 --deck-pairs-seed 7700 \
        --train-jsonl <git-show of episodes_v2.jsonl at 928e2fd~1> \
        --out /tmp/opencode/drift_probe.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from MTG_bot.core.executor.games import get_supply
from tools.search.champ_shadow import (
    DECK_PAIRS_SEED,
    DEFAULT_CKPT,
    run_champ_game,
    stream_words,
)
from tools.training import bc_data


class UnkSink:
    """Counts UNK landings over ask rows scored against one vocab."""

    def __init__(self, vocab: dict[str, int]) -> None:
        self.vocab = vocab
        self.unk = vocab[bc_data.UNK]
        self.asks = 0
        self.tokens = 0
        self.misses = 0
        self.oov: Counter = Counter()
        self.oov_asks: Counter = Counter()  # site kind -> asks containing UNK

    def score(self, what: str, obs: dict) -> None:
        words = stream_words(what, obs)
        miss = [w for w in words if self.vocab.get(w, self.unk) == self.unk]
        self.asks += 1
        self.tokens += len(words)
        self.misses += len(miss)
        for w in miss:
            self.oov[w] += 1
        if miss:
            self.oov_asks[what.split(":", 1)[0]] += 1

    def report(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        out = {
            "asks": self.asks,
            "tokens": self.tokens,
            "unk": self.misses,
            "unk_rate": round(self.misses / max(1, self.tokens), 4),
            "oov_distinct": len(self.oov),
            "asks_with_unk_share": round(
                sum(self.oov_asks.values()) / max(1, self.asks), 4
            ),
            "top_oov_families": [
                {"token": t, "count": c} for t, c in self.oov.most_common(10)
            ],
            "oov_by_site_kind": dict(self.oov_asks.most_common()),
        }
        if extra:
            out.update(extra)
        return out


def instrument_bcask(agent: Any) -> UnkSink:
    """Wrap THIS instance's ``_decide`` (shadowing the class method) to
    score every ask it answers. Returns the sink; the original decision is
    returned byte-for-byte — the wrapper observes, never interferes."""
    sink = UnkSink(agent.vocab)
    orig = agent._decide  # already bound: takes (torch, ctx)

    def _decide(torch: Any, ctx: Any) -> int:
        idx = orig(torch, ctx)
        sink.score(ctx.vocab, ctx.world)
        return idx

    # instance-dict lookup returns this closure AS-IS (no descriptor
    # binding), so plain (torch, ctx) params are correct — a MethodType
    # here would double-bind self.
    agent._decide = _decide  # type: ignore[method-assign]
    return sink


def score_training_rows(jsonl_path: Path, vocab: dict[str, int]) -> UnkSink:
    """The same UNK scoring over TRAINING corpus rows (every ask row of
    every episode, gold or not) under the checkpoint's own vocab."""
    sink = UnkSink(vocab)
    n_eps = 0
    with jsonl_path.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            ep = json.loads(line)
            n_eps += 1
            for row in ep["asks"]:
                sink.score(row["what"], row["obs"])
    return sink


def fetch_git_blob(rev_spec: str, dest: Path) -> Path:
    """Materialize ``git show REV:PATH`` once (training corpus of an era)."""
    if not dest.exists():
        blob = subprocess.run(
            ["git", "-C", str(REPO), "show", rev_spec],
            capture_output=True,
            text=True,
            check=True,
        )
        dest.write_text(blob.stdout)
    return dest


def run_probe(
    seeds: list[int],
    deck_pairs_seed: int,
    ckpt_spec: str,
    train_jsonl: Path,
    pool: str = "engine",
    opponent: str = "teacher",
    device: str = "cpu",
) -> dict[str, Any]:
    """Live side: replay ``seeds`` champion games with ``BcAsk._decide``
    instrumented. Train side: score the historical corpus rows. One vocab,
    one scorer, two eras."""
    import torch

    torch.set_num_threads(1)
    from tools.training.ab_duel import BcAsk

    blob_vocab = BcAsk.fresh(ckpt_spec, device).vocab
    supply = get_supply(pool)
    live = UnkSink(blob_vocab)
    games = []
    for seed in seeds:
        t0 = time.time()
        sinks: list[UnkSink] = []

        def hook(seat: int, agent: Any, sinks: list[UnkSink] = sinks) -> None:
            if seat == 0 and hasattr(agent, "vocab"):
                sinks.append(instrument_bcask(agent))

        g = run_champ_game(
            seed,
            supply=supply,
            ckpt_spec=ckpt_spec,
            opponent=opponent,
            deck_pairs_seed=deck_pairs_seed,
            device=device,
            agent_hook=hook,
        )
        assert sinks and sinks[0] is not None, f"probe not installed s{seed}"
        sink = sinks[0]
        live.asks += sink.asks
        live.tokens += sink.tokens
        live.misses += sink.misses
        live.oov.update(sink.oov)
        live.oov_asks.update(sink.oov_asks)
        games.append(
            {
                "seed": seed,
                "outcome": g["outcome"],
                "seat0_asks": g["counters"]["seat0_asks"],
                "scored_asks": sink.asks,
                "unk_rate": round(sink.misses / max(1, sink.tokens), 4),
                "crash": g["crash"],
                "seconds": round(time.time() - t0, 1),
            }
        )
        assert sink.asks == g["counters"]["seat0_asks"], (
            f"seed {seed}: instrumented {sink.asks} != recorded "
            f"{g['counters']['seat0_asks']} seat-0 asks"
        )
        assert g["counters"]["seat0_asks"] > 0, f"seed {seed}: no asks"

    train = score_training_rows(train_jsonl, blob_vocab)
    live_r = live.misses / max(1, live.tokens)
    train_r = train.misses / max(1, train.tokens)
    return {
        "ckpt": ckpt_spec,
        "vocab_size": len(blob_vocab),
        "pool": pool,
        "opponent": opponent,
        "deck_pairs_seed": deck_pairs_seed,
        "live": live.report({"games": games, "seeds": seeds}),
        "train": train.report({"corpus": str(train_jsonl)}),
        "headline": {
            "live_unk_rate": round(live_r, 4),
            "train_unk_rate": round(train_r, 4),
            "drift_ratio_live_over_train": (
                round(live_r / train_r, 2) if train_r > 0 else None
            ),
        },
    }


def write_report(res: dict[str, Any], path: Path) -> None:
    live, train, head = res["live"], res["train"], res["headline"]
    ratio = head["drift_ratio_live_over_train"]
    ratio_s = f"{ratio}x" if ratio is not None else "inf (train UNK = 0)"
    lines = [
        "# Drift probe — bc9-era vocab: live obs vs training rows",
        "",
        f"- ckpt: `{res['ckpt']}` (vocab {res['vocab_size']}), pool={res['pool']}",
        f"- LIVE  : {live['asks']} asks, {live['tokens']} stream tokens, "
        f"{live['unk']} UNK -> **UNK rate {live['unk_rate']}** "
        f"({live['asks_with_unk_share'] * 100:.1f}% of asks contain >=1 UNK)",
        f"- TRAIN : {train['asks']} rows, {train['tokens']} tokens, "
        f"{train['unk']} UNK -> **UNK rate {train['unk_rate']}**",
        f"- drift ratio live/train: **{ratio_s}**",
        "",
        "## Top OOV families (strings hashing to UNK)",
        "| live token | live count | train token | train count |",
        "|---|---|---|---|",
    ]
    L, T = live["top_oov_families"], train["top_oov_families"]
    for i in range(max(len(L), len(T))):
        l = f"{L[i]['token']} | {L[i]['count']}" if i < len(L) else " | "
        t = f"{T[i]['token']} | {T[i]['count']}" if i < len(T) else " | "
        lines.append(f"| {l} | {t} |")
    lines += [
        "",
        f"live OOV by site kind: `{json.dumps(live['oov_by_site_kind'])}`",
        "",
        "Verdict: live-UNK >> train-UNK => era tokenization mismatch is "
        "a real input-distribution hole for this checkpoint (/75 suspect (ii)).",
    ]
    path.write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="91,92", help="comma-separated game seeds")
    ap.add_argument("--deck-pairs-seed", type=int, default=DECK_PAIRS_SEED)
    ap.add_argument("--ckpt", default=DEFAULT_CKPT)
    ap.add_argument("--pool", default="engine", choices=("all", "engine", "castable"))
    ap.add_argument("--opponent", default="teacher")
    ap.add_argument("--device", default="cpu")
    ap.add_argument(
        "--train-rev",
        default="928e2fd~1:tools/training/episodes_v2.jsonl",
        help="git REV:PATH of the era-training corpus",
    )
    ap.add_argument(
        "--train-jsonl",
        type=Path,
        default=Path("/tmp/opencode/episodes_v2_train_era.jsonl"),
    )
    ap.add_argument("--out", type=Path, default=Path("/tmp/opencode/drift_probe.json"))
    args = ap.parse_args(argv)

    train_path = fetch_git_blob(args.train_rev, args.train_jsonl)
    res = run_probe(
        seeds=[int(s) for s in args.seeds.split(",")],
        deck_pairs_seed=args.deck_pairs_seed,
        ckpt_spec=args.ckpt,
        train_jsonl=train_path,
        pool=args.pool,
        opponent=args.opponent,
        device=args.device,
    )
    args.out.write_text(json.dumps(res, indent=1))
    report = args.out.parent / (args.out.stem + "_report.md")
    write_report(res, report)
    print(json.dumps(res["headline"], indent=1))
    print(f"wrote {args.out} and {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
