"""DESIGN_PRIORITY §4 item 2: answers that take away a target or a source.

On the probe's standard board (gate G1's, tools/cards/probe.py), every castable spell with card
targets and every activatable ability of a set's dealt cards is put on the stack with its player
holding priority (CR 117.3c); in response its card targets are exiled, or, for an ability, its
source is; then both players pass until the stack is empty. Any exception is a finding, and so is
a spell or ability whose every target was exiled that still resolved (CR 608.2b) or a stack left
non-empty. Choices take the first word. The probe's own traces are untouched.

    .venv/bin/python tools/cards/respond.py M21 [--limit N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from probe import WINDOW, Probe

from MTG_bot.core.ability_tree import ActivatedAbility
from MTG_bot.core.executor import GameOver
from MTG_bot.core.executor.games import get_supply
from MTG_bot.core.executor.legality import activate
from MTG_bot.core.executor.query import (
    activation_target_slots,
    legal_activations,
    legal_casts,
    spell_target_slots,
)
from MTG_bot.core.executor.stack import cast


def _first_word(vocab: tuple[str, ...], what: str) -> str:
    return "PASS" if what.startswith(WINDOW) and "PASS" in vocab else vocab[0]


def respond(probe: Probe, where: str, label: str, put, gone: list[str], every: bool) -> str | None:
    """Put the object on the stack holding priority (``put``), exile the pack cards ``gone`` in
    response, then pass until the stack is empty. ``every``: ``gone`` is every target, so the
    object must not resolve. Returns a finding, or None."""
    r = probe.runner(where)
    r.ex.decisions.provider = _first_word
    try:
        with r.ex.holding_priority():
            try:
                put(r)
            except ValueError as exc:  # the probe's combination is not a legal one: no case
                if "illegal" in str(exc):
                    return None
                raise
            r.ex._priority_check()
            for key in gone:
                r._dispatch_op({"op": "move", "key": key, "to": "exile"})
        start = len(r.ex.events)
        r.ex.fire_triggers()
    except GameOver:
        return None
    except Exception as exc:  # noqa: BLE001 - any raise is the finding
        return f"{label}: {type(exc).__name__}: {exc}"[:400]
    finally:
        r.ex.decisions.provider = None
    if r.ex.stack.frames:
        return f"{label}: the stack is not empty after both players passed"
    if every and not any(e[1] == "NO_LEGAL_TARGETS" for e in r.ex.events[start:]):
        return f"{label}: every target was exiled in response, yet it resolved"
    return None


def card_findings(probe: Probe) -> tuple[int, list[str]]:
    """(responses run, findings) for one card."""
    runs, found = 0, []
    r = probe.runner("hand")
    h = r.handles["card"]
    keys = {v: k for k, v in r.handles.items()}
    for row in [row for row in legal_casts(r.world, r.ex, r.p0) if row.handle == h and not row.land]:
        for modes in probe._modes(row.node):
            slots = list(spell_target_slots(r.ex, probe._mode_node(row.node, modes), spell_handle=h,
                                            seat=r.p0))
            if not slots or any(s.min_count > len(s.candidates) for s in slots):
                continue
            for targets in probe._target_sets(slots):
                cards = [keys[t] for t in targets if t in keys]
                if not cards:
                    continue

                def put(rr, t=targets, kicked=row.kicked, modes=modes) -> None:
                    cast(rr.ex, rr.p0, rr.handles["card"], kicked=kicked, mode_choices=modes,
                         targets=tuple(t), x=1 if probe._has_x() else None)

                runs += 1
                label = f"cast modes={list(modes)} targets={cards}"
                if msg := respond(probe, "hand", label, put, cards, len(cards) == len(targets)):
                    found.append(msg)
    for where in ("battlefield", "hand", "graveyard"):
        try:
            r = probe.runner(where)
        except GameOver:  # the card there alone ends the game as the first turn starts
            continue
        h = r.handles["card"]
        keys = {v: k for k, v in r.handles.items()}
        legal = {o.ability_idx for o in legal_activations(r.world, r.ex, r.p0) if o.source == h}
        for idx, ab in enumerate(probe.card.abilities):
            if not isinstance(ab, ActivatedAbility) or idx not in legal:
                continue
            slots = list(activation_target_slots(r.ex, ab.effect, source=h, seat=r.p0))
            if any(s.min_count > len(s.candidates) for s in slots):
                continue
            for targets in probe._target_sets(slots) or [()]:

                def put(rr, t=targets, idx=idx) -> None:
                    activate(rr.ex, rr.handles["card"], idx, seat=rr.p0, targets=tuple(t))

                # CR 113.7a: an ability on the stack exists apart from its source.
                runs += 1
                label = f"activate [{idx}] from {where}, then the source leaves"
                if msg := respond(probe, where, label, put, ["card"], False):
                    found.append(msg)
                cards = [keys[t] for t in targets if t in keys and keys[t] != "card"]
                if cards:
                    runs += 1
                    label = f"activate [{idx}] from {where} targets={cards}"
                    if msg := respond(probe, where, label, put, cards, len(cards) == len(targets)):
                        found.append(msg)
    return runs, found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("set")
    ap.add_argument("--limit", type=int, default=0, help="only the first N dealt cards by name")
    args = ap.parse_args(argv)
    supply = get_supply("all", args.set)
    oids = sorted(supply.playable_engine_ids, key=lambda o: supply.metas[o].name)
    if args.limit:
        oids = oids[: args.limit]
    total, bad = 0, 0
    for oid in oids:
        runs, found = card_findings(Probe(supply, args.set, oid))
        total += runs
        for msg in found:
            bad += 1
            print(f"{supply.metas[oid].name}: {msg}", flush=True)
    print(f"{args.set}: {len(oids)} cards, {total} responses, {bad} findings")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
