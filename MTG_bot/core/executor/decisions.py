"""The 14b decision channel — a VOCABULARY-ADDRESSED stream (B-4 ruling).

Round-14a ledger (/03 row B-4): every public op drained its trigger queue
with one flat positional ``trigger_decisions`` tuple the caller had to build
BEFORE the op ran. A land drop ARMS the land's own ETB trigger inside the
op, so the drain demanded a decision the caller could not legally have
enumerated — PC-7 v1 died on it 22/30 games. The owner ruling (doc
09-30/02 + the /03 proposal) rebuilds the channel as
``take(vocab, what)``: the producer tags vocabulary AT THE ASK, and every
answer is addressed to that (vocabulary, site) key.

Three supply lanes, consulted in this order (:class:`DecisionStream.take`
via :meth:`quantity.ExecCtx.take_decision`):

1. the per-op explicit POOL (the legacy ``decisions=`` kwarg — tree-order
   pre-supply for a KNOWN tree; byte-identical behaviour for every 12a-14a
   caller, and still validated against the asked vocabulary),
2. the per-(vocab, what) FIFO primed by a policy through
   :meth:`push` (the harness's enumeration-free lane: an answer queued
   under the key a mid-drain trigger asks with is picked up WHENEVER it
   arrives — zero prediction of which triggers arm),
3. the ASK-TIME provider the harness registers (:attr:`provider`) — the
   engine hands ``(vocab, what)`` to an EXTERNAL answerer at the exact
   moment of demand, the answer is re-validated against the vocabulary.

Exhaustion of all three lanes raises (C15/C16 — no engine-side default,
ever; the tripwire semantics are unchanged). The pool lane before the FIFO
lane is deliberate: with a pool supplied the behaviour is exactly the
pre-14b one, so no historical replay moves.

Why ask-time and not a pending-poll loop: a decision demand can occur
MID-resolution (a Seq's second atom asks after the first atom already
mutated the world), so the drain cannot suspend-and-refire without
re-executing those mutations. The provider answers at the demand point
instead — the same enumeration the query surface exposes, delivered at
the site that needs it. ``ask_log`` records every answered demand
(``what`` → ``answer``, ask order) for digests and introspection.

Determinism: the provider is a pure consumer of the CALLER's seeded rng
and the engine asks in a deterministic order, so a seed identifies the
whole decision history (the replay pin relies on that).
"""

from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Callable, Sequence

#: A decision is addressed by its vocabulary (the tokens the engine accepts)
#: and a stable site tag the producer passes at the ask (``may:<source>``,
#: ``scry:<player>:<n>``, ``choose:<source>:<digest>``, ``name:<source>`` …).
DecisionKey = tuple[tuple[str, ...], str]

#: Provider signature: receives the exact vocabulary and site tag the
#: engine is asking with, returns the answer token (re-validated by the
#: stream; a non-member raises exactly like a wrong pool token).
DecisionProvider = Callable[[tuple[str, ...], str], str]


def site_digest(payload: object) -> str:
    """Stable short digest of an enumeration payload (option-sets,
    candidate rows) for a choice site tag. Cross-run stable (sha1 of the
    repr — NOT the salted builtin hash()), so a replay's decision keys
    are identical (the replay pin relies on that)."""
    return hashlib.sha1(repr(payload).encode()).hexdigest()[:12]


class DecisionStream:
    """Per-(vocab, what) FIFOs + optional ask-time provider + ask log.

    Lives on the :class:`~MTG_bot.core.executor.Executor` (``.decisions``)
    and rides every ``ExecCtx`` the executor builds — effect contexts,
    trigger firings, payment contexts, replacement actions — which is what
    closes B-4: an ask that arrives mid-drain from a trigger the op itself
    armed reaches the SAME stream the policy controls.
    """

    def __init__(self) -> None:
        self._fifo: dict[DecisionKey, deque[str]] = {}
        #: (what, answer) per consumed decision, in ask order — the
        #: channel's own audit row (digests, C15 proof tests). PUBLIC
        #: lane: only genuine asks land here (T5-F1 — a forced
        #: single-option surface is auto-picked, never asked).
        self.ask_log: list[tuple[str, str]] = []
        #: (what, answer) per resolved demand in occurrence order, ASKED
        #: or silently auto-picked (offers.py T5-F1). History guards
        #: (MAY_DONE's "if you do") read this, so a forced skip still
        #: answers its rider instead of going loud.
        self.journal: list[tuple[str, str]] = []
        #: externally supplied answers for demands nothing pre-primed;
        #: None means exhaustion raises (C15: no hidden default).
        self.provider: DecisionProvider | None = None

    # ------------------------------------------------------------- supply

    def push(self, vocab: Sequence[str], what: str, *answers: str) -> None:
        """Prime the FIFO for one (vocab, what) key (ruling 5's explicit
        supply lane: an answer the policy can enumerate ahead of the ask)."""
        key: DecisionKey = (tuple(vocab), what)
        self._fifo.setdefault(key, deque()).extend(answers)

    def has(self, vocab: Sequence[str], what: str) -> bool:
        """Does the FIFO for this key hold an answer? (Pool-first callers —
        :meth:`quantity.ExecCtx.take_decision` — consult this after the
        explicit per-op pool is exhausted.)"""
        queue = self._fifo.get((tuple(vocab), what))
        return bool(queue)

    # --------------------------------------------------------------- demand

    def take(self, vocab: Sequence[str], what: str) -> str:
        """Pop the primed answer for the key, or consult the provider.

        Raises ``ValueError`` (same shapes the positional channel raised)
        when neither lane can answer or the answer is out of vocabulary —
        never a default."""
        key: DecisionKey = (tuple(vocab), what)
        queue = self._fifo.get(key)
        if queue:
            answer = queue.popleft()
        elif self.provider is not None:
            answer = self.provider(tuple(vocab), what)
        else:
            raise ValueError(
                f"executor: {what} needs a decision from {vocab}, "
                "nothing is primed and no answerer is registered"
            )
        if answer not in vocab:
            raise ValueError(f"executor: {what} decision {answer!r} not in {vocab}")
        self.ask_log.append((what, answer))
        self.journal.append((what, answer))
        return answer

    def answered(self) -> tuple[tuple[str, str], ...]:
        """The consumed decision history (what → answer, ask order)."""
        return tuple(self.ask_log)
