"""BC dataset: episode JSONL -> minimal token-id streams (training batch 1).

Schema per design doc 09 §1: one decision step =
``<ask> site-tag + obs-tokens <sep>``; the model reads the pack's steps as
one causal stream and points at the gold candidate at every gold ``<sep>``.

Tokenisation is INTENTIONALLY minimal — batch 1 validates the schema + the
training loop, not the featurizer: whitespace/lowercase word tokens over
{obs serialization words, candidate tokens}; the vocab is small (~hundreds
of entries) and saved with the checkpoint so eval is reproducible. The
candidate span carries NO positional information (permutation law §1: the
pointer score must be a function of content, not rank).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PAD, UNK, BOS, ASK, SEP = "<pad>", "<unk>", "<s>", "<ask>", "<sep>"
SPECIALS = [PAD, UNK, BOS, ASK, SEP]
SITE_KINDS = (
    "may",
    "scry",
    "choose",
    "name",
    "cw",
    "counter",
    "pay",
    "target",
    "mana",
    "block",
    "attack",
    "order",
    "trample",
    "policy",
    "quantity",
    "draw",
    "roll",
    # 2026-10-07 /38: promoted search picks (/29) + k-of-n (/31) + sacrifice costs
    # reached the ask channel but were tokenizing site:? — §10 blindness defect fixed;
    # additive kinds only (first-seen vocab order extends; episodes re-encoded).
    "one_of",
    "sacrifice",
)

_WORD = re.compile(r"[^0-9a-z']+")


def tokenize(text: str) -> list[str]:
    """Lowercase word split — the whole v1 featurizer."""
    return [w for w in _WORD.split(text.lower()) if w]


def _row_words(rows: list[list[str]]) -> list[str]:
    """Serialize card rows (handle token, name, tapped, counters) — the
    handle token splits through the SAME tokenizer as the candidate vocab,
    so a candidate ``card:17`` lexically binds to the obs row naming it."""
    words: list[str] = []
    for row in rows:
        for part in row:
            words += tokenize(part)
        words.append(";")
    return words


def obs_words(obs: dict[str, Any]) -> list[str]:
    """Deterministic word serialization of a packrec obs snapshot."""
    words = ["t", str(obs.get("turn", "?"))]
    for tag, key in (("act", "active"), ("seat", "seat")):
        v = obs.get(key)
        words += [tag, "?" if v is None else str(v)]
    src = obs.get("source")
    words += ["src"] + _row_words([src] if isinstance(src, list) else [])
    lives = obs.get("lives", [])
    hands = obs.get("hand", [])
    mana = obs.get("mana", [])
    bfs = obs.get("battlefield", [])
    gys = obs.get("graveyard", [])
    for i in range(max(len(lives), len(bfs), 1)):
        words += ["p", str(i)]
        if i < len(lives):
            words += ["life", str(lives[i])]
        if i < len(gys):
            words += ["gy", str(gys[i])]
        if i < len(mana) and mana[i]:
            words += ["mana"] + [f"{c}{n}" for c, n in mana[i].items()]
        if i < len(hands):
            words += ["hand"] + _row_words(hands[i])
        if i < len(bfs):
            words += ["on"] + _row_words(bfs[i])
    return words


#: row-grouped context: (class, seat, [(handle, words)]). Card-row word
#: fragments carry their trailing ``;``; section words do not.
Group = tuple[str, int | None, list[tuple[str | None, list[str]]]]


def flatten_groups(groups: list[Group]) -> list[str]:
    return [w for _k, _s, rows in groups for _h, ws in rows for w in ws]


def _row_frag(row: list[str]) -> tuple[str | None, list[str]]:
    words: list[str] = []
    for part in row:
        words += tokenize(part)
    words.append(";")
    return (str(row[0]) if row else None, words)


def obs_groups(obs: dict[str, Any]) -> list[Group]:
    """Row-grouped view of :func:`obs_words`: ``flatten_groups(obs_groups(o))
    == obs_words(o)`` for every obs (verified by test). Classes: ``hdr``
    (turn/act/seat/src — never a drop candidate), ``pmark``/``life``/``gycnt``
    /``mana`` (per-seat scalars, tiny, never dropped), ``hand`` and ``bf``
    (card-row groups, one row per fragment)."""
    groups: list[Group] = []
    hdr: list[tuple[str | None, list[str]]] = [(None, ["t", str(obs.get("turn", "?"))])]
    for tag, key in (("act", "active"), ("seat", "seat")):
        v = obs.get(key)
        hdr.append((None, [tag, "?" if v is None else str(v)]))
    src = obs.get("source")
    if isinstance(src, list):
        hdr.append((None, ["src"]))
        h, ws = _row_frag(src)
        hdr.append((h, ws))
    else:
        hdr.append((None, ["src"]))
    groups.append(("hdr", None, hdr))
    lives = obs.get("lives", [])
    hands = obs.get("hand", [])
    mana = obs.get("mana", [])
    bfs = obs.get("battlefield", [])
    gys = obs.get("graveyard", [])
    for i in range(max(len(lives), len(bfs), 1)):
        scal: list[Group] = [("pmark", i, [(None, ["p", str(i)])])]
        if i < len(lives):
            scal.append(("life", i, [(None, ["life", str(lives[i])])]))
        if i < len(gys):
            scal.append(("gycnt", i, [(None, ["gy", str(gys[i])])]))
        if i < len(mana) and mana[i]:
            scal.append(
                (
                    "mana",
                    i,
                    [(None, ["mana"] + [f"{c}{n}" for c, n in mana[i].items()])],
                )
            )
        groups.extend(scal)
        if i < len(hands):
            groups.append(
                ("hand", i, [(None, ["hand"])] + [_row_frag(r) for r in hands[i]])
            )
        if i < len(bfs):
            groups.append(("bf", i, [(None, ["on"])] + [_row_frag(r) for r in bfs[i]]))
    return groups


def site_words(what: str) -> list[str]:
    kind = what.split(":", 1)[0]
    return [f"site:{kind}" if kind in SITE_KINDS else "site:?"]


def build_vocab(episodes: list[dict[str, Any]]) -> dict[str, int]:
    vocab = {t: i for i, t in enumerate(SPECIALS)}
    for ep in episodes:
        for row in ep["asks"]:
            for w in site_words(row["what"]) + obs_words(row["obs"]):
                vocab.setdefault(w, len(vocab))
            for cand in row["candidates"]:
                for w in tokenize(cand) or [UNK]:
                    vocab.setdefault(w, len(vocab))
    return vocab


def encode_episode(ep: dict[str, Any], vocab: dict[str, int]) -> dict[str, Any]:
    """One episode -> token stream + gold pointer rows (ids, JSON-safe)."""
    unk = vocab[UNK]
    seq: list[int] = [vocab[BOS]]
    gold_rows: list[dict[str, Any]] = []
    for row in ep["asks"]:
        seq.append(vocab[ASK])
        for w in site_words(row["what"]) + obs_words(row["obs"]):
            seq.append(vocab.get(w, unk))
        seq.append(vocab[SEP])
        if row["gold"]:
            cands = []
            for cand in row["candidates"]:
                ids = [vocab.get(w, unk) for w in tokenize(cand)] or [unk]
                cands.append(ids)
            gold_rows.append(
                {
                    "pos": len(seq) - 1,  # the <sep> position = step summary
                    "ordinal": row["ordinal"],
                    "what": row["what"],
                    "candidates": row["candidates"],
                    "cand_ids": cands,
                    "is_pass": [c == "PASS" for c in row["candidates"]],
                    "gold_idx": row["gold_idx"],
                }
            )
    return {"pack": ep["pack"], "card": ep["card"], "seq": seq, "gold": gold_rows}


def load_episodes(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def build_dataset(
    episodes: list[dict[str, Any]], vocab: dict[str, int]
) -> list[dict[str, Any]]:
    return [encode_episode(ep, vocab) for ep in episodes]


def join_corpus(
    dataset: list[dict[str, Any]], corpus_items: list[dict[str, Any]]
) -> int:
    """Attach the cert floors (random/null/l1) to gold rows by
    (pack, per-pack order) — the extraction order both sides share. Returns
    the number of gold rows joined (119 expected; assert at the call site)."""
    by_pack: dict[str, list[dict[str, Any]]] = {}
    for item in corpus_items:
        by_pack.setdefault(item["pack"], []).append(item)
    joined = 0
    for ep in dataset:
        items = by_pack.get(ep["pack"], [])
        if len(items) != len(ep["gold"]):
            raise AssertionError(
                f"{ep['pack']}: {len(ep['gold'])} gold rows vs {len(items)} corpus items"
            )
        for row, item in zip(ep["gold"], items):
            if row["candidates"] != item["candidates"] or row["gold_idx"] != item[
                "candidates"
            ].index(item["gold"]):
                raise AssertionError(f"{ep['pack']}: gold row/item mismatch")
            row["cert"] = {
                "random": item["random"],
                "null": item["null"],
                "l1_ready": item["l1_ready"],
                "card": item["card"],
            }
            joined += 1
    return joined
