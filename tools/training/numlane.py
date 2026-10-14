"""Digit-tokenized numeric world-lanes — the /76 §8 tokenizer cure.

Problem (KNOWLEDGE/2026-10-13/76): every world-lane NUMBER (turn, life, gy
count, library length, handle index, counters) is a fixed literal vocab token,
so live value ranges outside the curated corpus go <unk> (33.5% of the
champion's live tokens). Fix: replace each standalone numeric word
(``^[0-9]{1,4}$``) with a composition ``dnum d#<d> d#<d> ...`` — unbounded
coverage from 11 reusable atoms.

Scope law (task 2026-10-13, owner):
* the transform applies to the SERIALIZED obs/site word stream only —
  the output of ``bc_data(_v2).obs_words(_groups)`` after tokenization;
* candidate MENU strings (``tokenize(cand)``) are never touched — choose
  index candidates "0"/"1" are positional labels, not world lanes;
* referent rows inside a grounded candidate span (the ``ref`` section,
  which duplicates world content) ARE transformed, so a handle-shaped
  candidate still binds lexically to its obs row through the digit lanes;
* gold positions (``gold_idx``, stream ``pos``) are ids, never words —
  untouched by construction.

Token design note: ``_WORD = [^0-9a-z']+`` splits on ``#``, so ``d#7`` can
NEVER survive ``tokenize()``. It therefore exists ONLY as a vocab key
produced by this module at stream level — it must never be embedded in a
string that gets tokenized. All call sites apply the transform AFTER
tokenization (bc_data_v2 ``obs_words_v2``/``obs_groups_v2``/
``cand_words_v2`` behind env flag NUMTOK=1).

Vocab extension + embedding transplant (resize call sites — exactly one
affected parameter, the pointer architecture has NO vocab-size output head):
* ``PointerBC.tok_emb`` — consumed by BOTH ``encode()`` (stream side) and
  ``candidate_emb()`` (mean-pool side); extending it covers every use.
* ``PointerBC.pos_emb`` is position-, not vocab-indexed — NOT resized.
Raw episode jsonl files are NEVER rewritten: the language is a per-process
property (NUMTOK=1), the data stays era-native.
* new rows: digit lanes init from the mean of existing ``d0``..``d9``
  vocab rows when present, else the <unk> row; plus N(0, 0.02) noise to
  break row symmetry. Existing rows transplant at IDENTICAL ids because
  :func:`extend_vocab` only appends.
"""

from __future__ import annotations

import os
import re
from typing import Any

#: env flag: "1" makes bc_data_v2 serialize numeric lanes digit-tokenized
NUMTOK_ENV = "NUMTOK"

#: marker opening every numeric composition (single out-of-band vocab token)
NUM_MARKER = "dnum"
#: prefix of every digit atom token: ``d#0`` .. ``d#9``
DIGIT_PREFIX = "d#"
#: a standalone numeric lane word (world-lane values are 0..9999)
NUM_RE = re.compile(r"^[0-9]{1,4}$")


def numtok_on() -> bool:
    """Read the flag at CALL time (never import time): gates, training and
    duels share one interpreter and must be able to flip lanes per process."""
    return os.environ.get(NUMTOK_ENV) == "1"


def digit_tokens() -> list[str]:
    """The new atom vocabulary, deterministic order."""
    return [NUM_MARKER] + [f"{DIGIT_PREFIX}{d}" for d in range(10)]


# ------------------------------------------------------------------ transform
def transform_words(words: list[str]) -> list[str]:
    """Replace every standalone ``^[0-9]{1,4}$`` word by its composition.
    Idempotent on already-transformed streams (no digit token re-expands)."""
    out: list[str] = []
    for w in words:
        if NUM_RE.match(w):
            out.append(NUM_MARKER)
            out += [f"{DIGIT_PREFIX}{c}" for c in w]
        else:
            out.append(w)
    return out


#: the per-ask row transform: ``row`` here is the row's serialized site+obs
#: word stream (what ``encode_episode_v2`` interleaves with ASK/SEP and what
#: ``BcAsk._forward_menu`` flattens). Candidates/gold never pass through it.
transform_bc_row = transform_words


def untransform_words(words: list[str]) -> list[str]:
    """Inverse: each ``dnum d#a d#b ...`` run collapses back to "ab".
    Used by the round-trip law and by drift probes reading ntk streams."""
    out: list[str] = []
    i, n = 0, len(words)
    while i < n:
        if words[i] == NUM_MARKER:
            digits: list[str] = []
            j = i + 1
            while j < n and words[j].startswith(DIGIT_PREFIX):
                digits.append(words[j][len(DIGIT_PREFIX) :])
                j += 1
            out.append("".join(digits) if digits else "0")
            i = j
        else:
            out.append(words[i])
            i += 1
    return out


def transform_groups(groups: list[Any]) -> list[Any]:
    """Same transform over ``bc_data.Group`` row-fragment lists (the BcAsk
    live lane). Fragment handle KEYS stay raw (lookup keys, not words)."""
    return [
        (k, s, [(h, transform_words(ws)) for h, ws in rows]) for k, s, rows in groups
    ]


# ------------------------------------------------------------- vocab extension
def extend_vocab(
    vocab: dict[str, int], extra_words: Any = None
) -> tuple[dict[str, int], list[str]]:
    """IN-FLIGHT extension: append the digit atoms (plus any first-seen
    ``extra_words`` not already present) at the END — existing ids never
    shift, so every transplanted embedding keeps its token.
    Returns ``(new_vocab, added_words)``; the original dict is untouched."""
    new = dict(vocab)
    added: list[str] = []
    for w in digit_tokens() + list(extra_words or ()):
        if w not in new:
            new[w] = len(new)
            added.append(w)
    return new, added


def resize_model_embeddings(
    model: Any, old_vocab: dict[str, int], new_vocab: dict[str, int], seed: int = 0
) -> int:
    """Grow ``tok_emb`` to ``len(new_vocab)`` rows IN-PLACE, transplanting
    old rows at identical ids. New rows init = mean of old ``d0``..``d9``
    rows if those tokens exist, else the <unk> row, + N(0, 0.02).
    Must run BEFORE ``load_state_dict`` of the old state — see
    :func:`transplant_state` for the canonical order. Returns n new rows."""
    import torch

    old_size = model.tok_emb.weight.shape[0]
    new_size = len(new_vocab)
    if new_size < old_size:
        raise ValueError(f"shrink not supported: {old_size} -> {new_size}")
    if new_size == old_size:
        return 0
    old_weight = model.tok_emb.weight.data
    donors = [
        old_vocab[t]
        for t in ("d0", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8", "d9")
        if t in old_vocab and old_vocab[t] < old_size
    ]
    donor_row = old_weight[old_vocab["<unk>"]].clone()
    if donors:
        donor_row = old_weight[donors].mean(0)
    emb = torch.nn.Embedding(new_size, model.tok_emb.weight.shape[1])
    emb.weight.data[:old_size] = old_weight[:old_size]
    gen = torch.Generator().manual_seed(seed)
    for tok, idx in new_vocab.items():
        if idx >= old_size:
            emb.weight.data[idx] = donor_row + 0.02 * torch.randn(
                model.tok_emb.weight.shape[1], generator=gen
            )
    model.tok_emb = emb
    return new_size - old_size


def transplant_state(
    model: Any,
    old_vocab: dict[str, int],
    new_vocab: dict[str, int],
    state: dict[str, Any],
    seed: int = 0,
) -> dict[str, Any]:
    """Load an OLD-vocab state_dict into a NEW-vocab model: widen the
    ``tok_emb.weight`` entry to the new row count with the donor-init rows
    (same rule as :func:`resize_model_embeddings`), and widen
    ``pos_emb.weight`` when the new ``max_len`` is larger (digit lanes
    inflate streams past the old table — /76 cure: 1024 -> 1536; appended
    position rows get the std=0.02 model init). Then load strict=True.
    Returns the (possibly widened) state for checkpointing."""
    import torch

    state = dict(state)
    gen = torch.Generator().manual_seed(seed)
    w = state["tok_emb.weight"]
    old_size = w.shape[0]
    new_size = len(new_vocab)
    if new_size < old_size:
        raise ValueError(f"shrink not supported: {old_size} -> {new_size}")
    if new_size != old_size:
        donors = [
            old_vocab[t]
            for t in ("d0", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8", "d9")
            if t in old_vocab and old_vocab[t] < old_size
        ]
        donor_row = w[old_vocab["<unk>"]].clone()
        if donors:
            donor_row = w[donors].mean(0)
        wide = torch.zeros(new_size, w.shape[1], dtype=w.dtype)
        wide[:old_size] = w
        for tok, idx in new_vocab.items():
            if idx >= old_size:
                wide[idx] = donor_row + 0.02 * torch.randn(w.shape[1], generator=gen)
        state["tok_emb.weight"] = wide
    p = state["pos_emb.weight"]
    rows = int(model.pos_emb.weight.shape[0])
    if p.shape[0] < rows:
        wide_p = 0.02 * torch.randn(rows, p.shape[1], dtype=p.dtype, generator=gen)
        wide_p[: p.shape[0]] = p
        state["pos_emb.weight"] = wide_p
    model.load_state_dict(state)
    return state
