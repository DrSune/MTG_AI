"""Batched multi-seat net inference for on-policy rollouts (/79 cost gate, 2026-10-14).

The /79 pilot measured 90.9 s/ask CPU because every rollout-seat ask paid a
FRESH single-row forward. This module keeps ONE model instance per process
(already the ``BcAsk.fresh`` law) and evaluates ALL parked rollout seats'
current-position decisions in ONE batched ``PointerBC.forward`` per rollout
step.

Three parts:

* :func:`prepare_row` — the row-building mirror of
  ``ab_duel.BcAsk._forward_menu_enc`` (relevance ladder, per-ASK block
  commit, candidate spans). tools/training is contractually untouched, so the
  encode lives here and its equivalence to the single path is a TESTED
  invariant (batched == per-seat decisions on the same position), not an
  assumption. Padding law mirrors ``bc_model.collate``: token 0 = ``<pad>``,
  ``pad_mask`` True = padding slot — a single-row batch builds byte-identical
  tensors to the single-row path.
* :class:`NetBatcher` — cooperative lockstep across rollout threads. A net
  seat's ``decide()`` parks its row; the LAST thread to park (or the last to
  leave) runs one batched forward for every parked seat and wakes them.
  Determinism: each seat's causal stream sees the same contexts in the same
  order regardless of interleaving (a seat only ever sees its own asks), so
  only the forward's batching changes; UCB allocation stays exact because
  the mcts scheduler still joins pulls in pull order before each pick.
* :func:`rollout_many` — runs forked rollouts concurrently through the
  plain :func:`rollout.rollout` loop (seat policies are ``_BatchedSeat``
  proxies); the engine loop itself is never forked or reordered.

A batched-forward failure is delivered to EVERY parked seat (its rollout is
recorded ``crash`` by the existing discipline) — never silently retried with
a corrupted stream.
"""

from __future__ import annotations

import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.search.rollout import RolloutResult, rollout
from tools.training import bc_data, bc_data_v2, numlane
from tools.training.ab_duel import BcAsk, _block_ids, _build_block, _cards_rows_of

# ----------------------------------------------------------------- row build


def prepare_row(bc: BcAsk, ctx: Any) -> dict[str, Any]:
    """Encode one ask for seat ``bc`` into plain python id lists and COMMIT
    the ask block to the seat's causal stream, exactly as
    ``BcAsk._forward_menu_enc`` does (same ladder, same truncation ledger,
    same assert). Caller wraps this in the checkpoint's NUMTOK env swap."""
    vocab = bc.vocab
    unk = vocab[bc_data.UNK]
    v2 = bc.schema == "v2"
    groups = (
        [
            ("ask", None, [(None, [bc_data.ASK])]),
            ("site", None, [(None, bc_data.site_words(ctx.vocab))]),
        ]
        + (bc_data_v2.obs_groups_v2(ctx.world) if v2 else bc_data.obs_groups(ctx.world))
        + [("sep", None, [(None, [bc_data.SEP])])]
    )
    current = _build_block(groups, vocab, unk)

    asking = ctx.world.get("_seat", ctx.world.get("seat"))
    if not isinstance(asking, int):
        asking = None
    fit = bc._assemble(current, list(ctx.candidates), asking)
    if fit is None:  # stage D: legacy tail window (never observed in-game)
        flat = [t for b in bc.blocks + [current] for t in _block_ids(b)]
        bc.seq = [vocab[bc_data.BOS]] + flat[-(bc.max_len - 1) :]
        bc.truncations += 1
        bc.ctx_stats["tail_fallbacks"] += 1
    else:
        hist, cur, sev, _dups, _blocks = fit
        if sev != "intact" or len(hist) != len(bc.blocks):
            bc.truncations += 1
        bc.blocks = hist + [cur]
        bc.seq = [vocab[bc_data.BOS]] + [t for b in bc.blocks for t in _block_ids(b)]
        assert len(bc.seq) <= bc.max_len
    sep = len(bc.seq) - 1

    cands = list(ctx.candidates)
    if v2:
        ground = bc_data_v2.ground_with(_cards_rows_of(ctx.world), ctx.vocab, cands)
        spans = [
            bc_data_v2.cand_words_v2(c, ground[ci] if ci < len(ground) else [])
            for ci, c in enumerate(cands)
        ]
    else:
        spans = [bc_data.tokenize(c) or [bc_data.UNK] for c in cands]
    cand_ids = [[vocab.get(w, unk) for w in words] or [unk] for words in spans]
    return {
        "seq": list(bc.seq),
        "sep": sep,
        "cand_ids": cand_ids,
        "is_pass": [c == "PASS" for c in cands],
    }


def _collate(torch: Any, rows: list[dict], device: Any) -> dict:
    """Pad prepared rows into one forward's tensors (bc_model.collate law:
    token 0 = <pad>, cand slot 0 = <pad>, pad_mask True = padding)."""
    b = len(rows)
    t_max = max(len(r["seq"]) for r in rows)
    c_max = max(len(r["cand_ids"]) for r in rows)
    l_max = max((len(ids) for r in rows for ids in r["cand_ids"]), default=1)
    tokens = torch.zeros(b, t_max, dtype=torch.long)
    pad_mask = torch.ones(b, t_max, dtype=torch.bool)
    cand_ids = torch.zeros(b, c_max, l_max, dtype=torch.long)
    cand_mask = torch.zeros(b, c_max, l_max, dtype=torch.bool)
    is_pass = torch.zeros(b, c_max, dtype=torch.bool)
    for i, r in enumerate(rows):
        ids = torch.tensor(r["seq"], dtype=torch.long)
        tokens[i, : len(ids)] = ids
        pad_mask[i, : len(ids)] = False  # single row -> all-False, as single path
        for ci, words in enumerate(r["cand_ids"]):
            t = torch.tensor(words, dtype=torch.long)
            cand_ids[i, ci, : len(t)] = t
            cand_mask[i, ci, : len(t)] = True
        for ci, p in enumerate(r["is_pass"]):
            is_pass[i, ci] = p
    to = lambda x: x.to(device)
    return {
        "tokens": to(tokens),
        "pad_mask": to(pad_mask),
        "gold_batch": torch.arange(b, device=device),
        "gold_pos": to(torch.tensor([r["sep"] for r in rows], dtype=torch.long)),
        "cand_ids": to(cand_ids),
        "cand_mask": to(cand_mask),
        "is_pass": to(is_pass),
    }


def batch_decide(items: list[tuple[BcAsk, Any]]) -> list[int]:
    """One batched forward scoring every ``(BcAsk, AskContext)`` row; returns
    each seat's pointer argmax (same torch.argmax tie law as ``BcAsk.decide``).
    All seats of one batch share the checkpoint -> one NUMTOK env swap."""
    import torch

    if not items:
        return []
    numtok = items[0][0].numtok
    prev = os.environ.get(numlane.NUMTOK_ENV)
    if numtok:
        os.environ[numlane.NUMTOK_ENV] = "1"
    else:
        os.environ.pop(numlane.NUMTOK_ENV, None)
    try:
        rows = [prepare_row(bc, ctx) for bc, ctx in items]
    finally:
        if prev is None:
            os.environ.pop(numlane.NUMTOK_ENV, None)
        else:
            os.environ[numlane.NUMTOK_ENV] = prev
    model = items[0][0].model
    device = next(model.parameters()).device
    t = _collate(torch, rows, device)
    with torch.no_grad():
        out = model.forward(
            t["tokens"],
            t["pad_mask"],
            t["gold_batch"],
            t["gold_pos"],
            t["cand_ids"],
            t["cand_mask"],
            t["is_pass"],
        )
    return [int(i) for i in out.argmax(-1)]


# ------------------------------------------------------------- coordinator


class _Slot:
    __slots__ = ("err", "res")

    def __init__(self) -> None:
        self.res: int | None = None
        self.err: BaseException | None = None


class NetBatcher:
    """Lockstep coordinator for concurrent net-rollout threads (see module
    docstring). Every net-seat decision funnels through :meth:`decide`; the
    last thread to park (or to leave) runs one batched forward for all parked
    rows and wakes the rest."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self.alive = 0  # registered threads not yet finished
        self._parked = 0
        self._pending: list[tuple[BcAsk, Any, _Slot]] = []

    def begin_thread(self) -> None:
        with self._cond:
            self.alive += 1

    def end_thread(self) -> None:
        with self._cond:
            self.alive -= 1
            batch = self._take_batch_locked()
        if batch:
            self._run_batch(batch)

    def decide(self, bc: Any, ctx: Any) -> int:
        slot = _Slot()
        with self._cond:
            self._pending.append((bc, ctx, slot))
            self._parked += 1
            batch = self._take_batch_locked()
            while batch is None and slot.res is None and slot.err is None:
                self._cond.wait()
        if batch:
            self._run_batch(batch)  # I am the last parked: forward for everyone
        if slot.err is not None:
            raise slot.err
        assert slot.res is not None, "NetBatcher: slot never resolved"
        return slot.res

    def _take_batch_locked(self) -> list | None:
        """Under the lock: every alive thread is parked and rows are waiting
        -> the caller runs the batch (parked reset covers those slots)."""
        if self._pending and self._parked >= self.alive:
            batch = self._pending
            self._pending = []
            self._parked = 0
            return batch
        return None

    def _run_batch(self, batch: list) -> None:
        try:
            res = batch_decide([(bc, ctx) for bc, ctx, _s in batch])
        except BaseException as err:  # noqa: BLE001 - deliver, never swallow
            with self._cond:
                for *_rest, slot in batch:
                    slot.err = err
                self._cond.notify_all()
            return
        with self._cond:
            for (*_rest, slot), i in zip(batch, res):
                slot.res = i
            self._cond.notify_all()


class _BatchedSeat:
    """A net rollout seat whose decide() goes through the shared batcher."""

    def __init__(self, bc: BcAsk, batcher: NetBatcher) -> None:
        self.bc, self.batcher = bc, batcher

    def decide(self, ctx: Any) -> int:
        return self.batcher.decide(self.bc, ctx)


# ---------------------------------------------------------------- scheduler


def rollout_many(
    states: list[Any],
    seat_specs: list[dict[int, BcAsk]],
    seeds: list[int],
    turn_cap: int,
    batcher: NetBatcher,
) -> list[RolloutResult]:
    """Play the forked rollouts concurrently on the UNCHANGED rollout loop,
    routing every seat's net decision through ``batcher``. Returns results in
    pull order. Seat BcAsk instances must already be fresh (created after the
    caller warmed the model cache — no lazy load inside threads)."""

    def play(i: int) -> RolloutResult:
        batcher.begin_thread()
        try:
            pols = {s: _BatchedSeat(bc, batcher) for s, bc in seat_specs[i].items()}
            return rollout(states[i], pols, seeds[i], turn_cap)
        finally:
            batcher.end_thread()

    with ThreadPoolExecutor(max_workers=len(states)) as ex:
        return [f.result() for f in [ex.submit(play, i) for i in range(len(states))]]
