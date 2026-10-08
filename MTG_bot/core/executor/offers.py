"""T5-F1 — the shared phantom-offer gate (§10 menu-visibility law).

§10's PHANTOM violation class: an encoding/ask that presents a decision the
engine resolves anyway. A one-word offer surface (``("0",)`` after a bounds
clamp, ``("skip",)`` after the CR 117.3 narrowing of ``optional_offer``) is
such an ask — there is exactly one legal answer, so asking bills the pack
and the BC stream for a decision nobody makes (and, worse, mis-pairs
vocabulary-addressed FIFO primings that key on the site).

The rule is the one ``stack.py`` forced auto-designation already runs at
cast time (CR 601.2c, stack.py:442): a single option the bounds force is
CONSUMED, never presented. This module lifts that rule from the target
lane into the decision channel: :func:`offer_or_autopick` is THE way any
decision generator presents an offer surface.

Journal semantics (owner ruling T5-F1): a silent consume writes to
:meth:`DecisionStream.journal` — the ordered audit of EVERY resolved
demand, asked or auto-picked — and NEVER to ``ask_log`` (the public lane
BC/rollout recorders consume; a phantom row there is what this fix
eliminates). MAY_DONE and other history guards read the journal, so an
auto-resolved may-offer still answers "if you do" — FALSE on a forced
skip — instead of going loud as an unanswered question.

The zero-candidate edge is an explicit site-contract error: an empty ask
has no answer to validate, so the PRODUCING site must gate before
offering (mirrors the pre-fix exhaustion raise, attributed to its owner).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from MTG_bot.core.executor.decisions import DecisionStream


class DecisionSite(Protocol):
    """The demand-site interface :func:`offer_or_autopick` consumes — the
    slice of :class:`~MTG_bot.core.executor.quantity.ExecCtx` the gate
    touches (kept structural so test stubs satisfy it without inheritance)."""

    stream: DecisionStream | None

    def take_decision(self, vocab: tuple[str, ...], what: str) -> str: ...


def offer_or_autopick(ctx: DecisionSite, vocab: tuple[str, ...], what: str) -> str:
    """Present a decision surface; auto-pick when the bounds force it.

    * ``len(vocab) == 1`` — the surface is FORCED: consume the single
      token silently, journal the consumption, and never emit an ask
      (no provider call, no FIFO pop, no pool word — the pool cursor does
      not move, so a pack word scripted for a phantom stays parked for
      whoever needs a real decision).
    * ``len(vocab) == 0`` — raise: zero legal options is a producer
      contract violation, not a decision.
    * else — the ordinary :meth:`ExecCtx.take_decision` lane, unchanged.
    """
    if len(vocab) == 1:
        answer = vocab[0]
        if ctx.stream is not None:
            ctx.stream.journal.append((what, answer))
        return answer
    if not vocab:
        raise ValueError(
            f"executor: {what} has an EMPTY offer surface (zero legal options): "
            "the producing site must gate before offering — an empty ask has "
            "no answer to validate (C15)."
        )
    return ctx.take_decision(vocab, what)
