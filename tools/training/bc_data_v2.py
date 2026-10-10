"""Observation schema v2: candidate grounding + fuller zones (batch 2).

Batch 1's honest null (KNOWLEDGE/2026-10-05/10-batch1-bc-floor.md) traced
the holdout failure to ungrounded candidates: 155/357 candidate surfaces
had ZERO tokens in the obs stream — handle candidates pointing into zones
the snapshot never serialized (library absent, graveyard counts-only) and
the 44 ``choose`` index candidates (``"0"/"1"``) whose referent pool is
invisible to the scorer. v2 is an OBSERVATION-ONLY fix: no decision
logic, no engine edit, corpus candidates stay byte-identical.

1. ZONES. Per seat: ``library`` top-6 (top-first — ``ZoneState.entries``
   pops from the end, so the reversed list is the real scry order),
   graveyard rows (newest-8), exile rows (newest-12). Omniscient-v1
   stance unchanged: the C2 masked view is a drop-in deletion.
2. GROUNDING. Every gold-row candidate carries its referent card rows as
   EXTRA span tokens: ``tokenize(cand) + ["ref"] + row_words(referents)``.
   Handles bind through ``world.cards`` (zone-independent); ``choose``
   indices bind through the digest stash below. The pointer scorer
   mean-pools candidate tokens with NO positional signal (bc_model
   §1 permutation law), so appended content tokens are schema-legal and
   the vocab prefix of every candidate stays byte-identical to v1.
3. CHOOSE DIGEST STASH. The CHOOSE handler asks with
   ``what = f"choose:{source}:{site_digest(tuple(rows))}"``
   (verbs.py:1427) where ``rows`` is the pool returned by
   ``query.verb_choose_options``. The handler imports that function
   LAZILY (verbs.py:1389), so patching the module attribute is seen by
   every call. ``install_choose_stash()`` wraps it with a PURE memo —
   stash ``site_digest(rows) -> rows`` (capped FIFO), return the value
   untouched. At ask time the trailing 12-hex digest of ``what``
   recovers the pool; the engine never observes the wrapper.

Run-side entry points: :func:`obs_words_v2`, :func:`build_vocab_v2`,
:func:`encode_episode_v2` (training) and :func:`ground_with` (duel).
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import MTG_bot.core.executor as _executor_pkg
from MTG_bot.core.executor import query as _query
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.identity import Handle

from tools.training import bc_data
from tools.training.bc_data import (  # re-export the v1 primitives
    ASK,
    BOS,
    PAD,
    SEP,
    UNK,
    SITE_KINDS,
    SPECIALS,
    _row_words,
    load_episodes,
    site_words,
    tokenize,
)

#: word separating a candidate's own tokens from its referent-row tokens
REF = "ref"

#: per-seat serialization caps (zones are omniscient context, not a dump)
LIB_CAP = 6
GY_CAP = 8
EXILE_CAP = 12

#: digest-stash size (one replay never holds >1 live choose pool)
STASH_CAP = 32


# ------------------------------------------------------------------ zones
def zone_rows_v2(obs: dict[str, Any]) -> list[str]:
    """The v2 DELTA words only: library / graveyard / exile rows per seat.

    Consumed by :func:`obs_words_v2`; keys absent or empty serialize to
    nothing (every ask pays only the zones that actually have cards)."""
    words: list[str] = []
    for tag, key in (("lib", "library"), ("gyr", "graveyard_rows"), ("exl", "exile")):
        for i, rows in enumerate(obs.get(key, [])):
            if rows:
                words += [tag, str(i)] + _row_words(rows)
    return words


def obs_words_v2(obs: dict[str, Any]) -> list[str]:
    """v1 serialization (untouched) followed by the v2 zone delta."""
    return bc_data.obs_words(obs) + zone_rows_v2(obs)


def zone_groups_v2(obs: dict[str, Any]) -> list[bc_data.Group]:
    """Row-grouped view of :func:`zone_rows_v2`: one lane group per
    (tag, seat) with a ``[tag, seat]`` marker fragment and one fragment per
    card row keyed by its handle. Empty lanes emit no group — flattening
    reproduces :func:`zone_rows_v2` exactly."""
    groups: list[bc_data.Group] = []
    for tag, key in (("lib", "library"), ("gyr", "graveyard_rows"), ("exl", "exile")):
        for i, rows in enumerate(obs.get(key, [])):
            if rows:
                frags: list[tuple[str | None, list[str]]] = [(None, [tag, str(i)])]
                frags += [bc_data._row_frag(r) for r in rows]
                groups.append((tag, i, frags))
    return groups


def obs_groups_v2(obs: dict[str, Any]) -> list[bc_data.Group]:
    """Row-grouped :func:`obs_words_v2` (v1 groups + zone lane groups)."""
    return bc_data.obs_groups(obs) + zone_groups_v2(obs)


# ------------------------------------------------------------- grounding
def _handle_of(token: str) -> Handle | None:
    """``"card:17"`` -> ``Handle("card", 17)`` (world.cards keys Handles,
    not strings — identity.py); None when the token is not handle-shaped."""
    ns, sep, idx = token.rpartition(":")
    if not sep or not ns:
        return None
    try:
        return Handle(ns, int(idx))
    except ValueError:
        return None


def card_row_lookup(world: Any) -> Callable[[str], list[str] | None]:
    """Handle token -> card row over the WHOLE world (zone-independent):
    ``world.cards`` knows every handle, so a hidden-zone candidate still
    grounds to ``[handle, name, tapped?, counters…]``."""

    def rows_of(token: str) -> list[str] | None:
        handle = _handle_of(token)
        if handle is None:
            return None
        state = world.cards.get(handle)
        if state is None:
            return None
        row = [str(handle), str(state.identity.name)]
        if state.tapped:
            row.append("tapped")
        for k, v in sorted(state.counters.items()):
            row.append(f"{k}={v}")
        return row

    return rows_of


def ground_with(
    rows_of: Callable[[str], list[str] | None],
    what: str,
    candidates: list[str] | tuple[str, ...],
) -> list[list[list[str]]]:
    """Per-candidate referent rows (``[]`` where no referent exists).

    * handle-shaped candidate -> its own card row (all 87 v1 handles);
    * ``choose`` index candidate -> the digest-stashed referent: card rows
      for the ATOM lane (pool members are handles), serialized effect
      words for the Choose-NODE lane (candidates are OPTION-SETs);
    * ``choose`` handle alias -> the pool row whose singleton handle it is;
    * content words (PASS / top / bottom / …) -> ``[]`` (already worded)."""
    entry = stash_rows_for(what)
    out: list[list[list[str]]] = []
    for cand in candidates:
        row = rows_of(cand)
        if row is not None:
            out.append([row])
            continue
        if entry is not None:
            pool, expand = entry
            hit: list[list[str]] | None = None
            if cand.isdigit() and int(cand) < len(pool):
                if expand:  # atom lane: pool row = handles -> card rows
                    hit = [(rows_of(h) or [h]) for r in pool[int(cand)] for h in r]
                else:  # node lane: pool row = the option-set's effect words
                    hit = [pool[int(cand)]]
            elif expand:
                for prole in pool:
                    if len(prole) == 1 and prole[0] == cand:
                        hit = [(rows_of(cand) or [cand])]
                        break
            if hit:
                out.append(hit)
                continue
        out.append([])
    return out


def ground_candidates(
    world: Any, what: str, candidates: list[str] | tuple[str, ...]
) -> list[list[list[str]]]:
    """Recorder-side convenience: grounding straight off a live ExecCtx
    world (the duel uses :func:`ground_with` over a snapshot card table)."""
    if world is None:
        return [[] for _ in candidates]
    return ground_with(card_row_lookup(world), what, candidates)


# --------------------------------------------------- choose digest stash
#
# Two engine lanes ask with ``choose:`` tags and BOTH digests are
# content-addressed over the pool payload, so a PURE memo on each lane's
# enumeration function recovers the referent at ask time:
#
# * ATOM lane (verbs.py:1389/1427, LAZY import): pool of card rows
#   (``verb_choose_options`` -> tuple[tuple[Handle]]); candidates index
#   INTO cards — grounded via world.cards like any handle.
# * CHOOSE-NODE lane (executor/__init__.py:149 top-level import, call
#   site ~862): the candidate is an OPTION-SET (tuple of printed-option
#   indices; the digest is over those indices, so every binary choose
#   shares one key — the pool is recovered per-ASK from the live memo).
#   Its referent is the compiled EFFECT of each option; we serialize the
#   dataclass/enum NAME BAG (verb/keyword/zone/filter words — exactly
#   the printed-option semantics the pointer scorer can bind on).
_STASH: dict[str, tuple[list[list[str]], bool]] = {}
_ORIG_VCO = _query.verb_choose_options
_ORIG_CO_QUERY = _query.choose_options
_ORIG_CO_EXEC = getattr(_executor_pkg, "choose_options")
_INSTALLED = False


def effect_words(effect: Any, cap: int = 24) -> list[str]:
    """Deterministic name-bag of a compiled effect: deduped lowercased
    dataclass class-names and enum names, walk order, capped. Content
    only — no ids, no numbers, cross-run stable (no hash()/repr memory
    addresses: enum names and class names only)."""
    words: list[str] = []

    def walk(node: Any) -> None:
        if len(words) >= cap:
            return
        if isinstance(node, Enum):
            w = node.name.lower()
            if w not in words:
                words.append(w)
            return
        if dataclasses.is_dataclass(node) and not isinstance(node, type):
            w = type(node).__name__.lower()
            if w not in words:
                words.append(w)
            for f in dataclasses.fields(node):
                walk(getattr(node, f.name, None))
            return
        if isinstance(node, (tuple, list)):
            for item in node:
                walk(item)

    walk(effect)
    return words[:cap]


def install_choose_stash() -> None:
    """Idempotent PURE memos around both enumeration lanes (see above).
    No behaviour change: every wrapper returns the original result object
    untouched."""
    global _INSTALLED
    if _INSTALLED:
        return
    _query.verb_choose_options = _stashing_vco  # type: ignore[attr-defined]
    _query.choose_options = _stashing_choose_options  # type: ignore[attr-defined]
    _executor_pkg.choose_options = _stashing_choose_options  # type: ignore[attr-defined]
    _INSTALLED = True


def uninstall_choose_stash() -> None:
    global _INSTALLED
    if _INSTALLED:
        _query.verb_choose_options = _ORIG_VCO  # type: ignore[attr-defined]
        _query.choose_options = _ORIG_CO_QUERY  # type: ignore[attr-defined]
        _executor_pkg.choose_options = _ORIG_CO_EXEC  # type: ignore[attr-defined]
        _INSTALLED = False


def _stashing_vco(executor: Any, atom: Any, **kw: Any) -> Any:
    rows = _ORIG_VCO(executor, atom, **kw)
    try:
        # the handler digests the RAW payload (repr of Handle objects);
        # key exactly like it does, and keep a str-canonical twin.
        alt = site_digest(tuple(rows))
        key = site_digest(tuple(tuple(str(h) for h in r) for r in rows))
        payload = [[str(h) for h in r] for r in rows]
        for k in {key, alt}:
            _STASH[k] = (payload, True)
        while len(_STASH) > STASH_CAP:
            _STASH.pop(next(iter(_STASH)))
    except Exception:  # noqa: BLE001 - a failed memo must never break play
        pass
    return rows


def _stashing_choose_options(executor: Any, choose: Any, **kw: Any) -> Any:
    opts = _ORIG_CO_QUERY(executor, choose, **kw)
    try:
        key = site_digest(tuple(o.option_idxs for o in opts))
        payload = []
        for opt in opts:
            row = ["set"]
            for idx in opt.option_idxs:
                row += effect_words(opt.choose.options[idx])
            payload.append(row[: 2 * 24])
        _STASH[key] = (payload, False)
        while len(_STASH) > STASH_CAP:
            _STASH.pop(next(iter(_STASH)))
    except Exception:  # noqa: BLE001
        pass
    return opts


def stash_rows_for(what: str) -> tuple[list[list[str]], bool] | None:
    """Recover ``(pool, expand_handles)`` from the ``what`` tag digest."""
    if not what.startswith("choose:"):
        return None
    digest = what.rsplit(":", 1)[-1]
    if len(digest) != 12 or not all(c in "0123456789abcdef" for c in digest):
        return None
    return _STASH.get(digest)


# ------------------------------------------------------------- encoding
def cand_words_v2(cand: str, ground: list[list[str]]) -> list[str]:
    """Candidate span words: the v1 tokens, then ``ref`` + referent rows."""
    words = tokenize(cand) or [UNK]
    if ground:
        words += [REF] + _row_words(ground)
    return words


def build_vocab_v2(episodes: list[dict[str, Any]]) -> dict[str, int]:
    vocab = {t: i for i, t in enumerate(SPECIALS)}
    for ep in episodes:
        for row in ep["asks"]:
            for w in site_words(row["what"]) + obs_words_v2(row["obs"]):
                vocab.setdefault(w, len(vocab))
            ground = row.get("ground", ())
            for ci, cand in enumerate(row["candidates"]):
                g = ground[ci] if ci < len(ground) else []
                if row["gold"]:
                    for w in cand_words_v2(cand, g):
                        vocab.setdefault(w, len(vocab))
                elif tokenize(cand):
                    for w in tokenize(cand):
                        vocab.setdefault(w, len(vocab))
    return vocab


def encode_episode_v2(ep: dict[str, Any], vocab: dict[str, int]) -> dict[str, Any]:
    """Same stream construction as v1; gold rows additionally carry the
    grounded candidate spans (``cand_ids`` vocab-prefix == v1 prefix)."""
    unk = vocab[UNK]
    seq: list[int] = [vocab[BOS]]
    gold_rows: list[dict[str, Any]] = []
    for row in ep["asks"]:
        seq.append(vocab[ASK])
        for w in site_words(row["what"]) + obs_words_v2(row["obs"]):
            seq.append(vocab.get(w, unk))
        seq.append(vocab[SEP])
        if row["gold"]:
            ground = row.get("ground", ())
            cands = []
            for ci, cand in enumerate(row["candidates"]):
                g = ground[ci] if ci < len(ground) else []
                ids = [vocab.get(w, unk) for w in cand_words_v2(cand, g)] or [unk]
                cands.append(ids)
            gold_rows.append(
                {
                    "pos": len(seq) - 1,
                    "ordinal": row["ordinal"],
                    "what": row["what"],
                    "candidates": row["candidates"],
                    "cand_ids": cands,
                    "is_pass": [c == "PASS" for c in row["candidates"]],
                    "gold_idx": row["gold_idx"],
                }
            )
    return {"pack": ep["pack"], "card": ep["card"], "seq": seq, "gold": gold_rows}


def build_dataset_v2(
    episodes: list[dict[str, Any]], vocab: dict[str, int]
) -> list[dict[str, Any]]:
    return [encode_episode_v2(ep, vocab) for ep in episodes]


join_corpus = bc_data.join_corpus  # corpus join is schema-agnostic (v1 law)

REPO = Path(__file__).resolve().parents[2]
