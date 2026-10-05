"""Pack-episode recorder: scenario packs -> decision-line episodes for BC.

Training batch 1 (design doc 09 §1/§5, S1 floor test). One **episode** is one
decision-bearing scenario pack replayed on its GOLD line (the scripted
``decisions`` words), with one recorded row per engine ask:

    {ordinal, what, candidates (canonical vocab order), answer, gold, obs}

``gold`` marks the asks whose answer was CONSUMED from the step's scripted
``decisions`` lane — those rows are the supervised targets; every ask (also
the harness-internal ones) stays in the sequence as decision context.

NO ENGINE EDIT. The capture rides ``tools/audit/puzzle_cert.py``'s
single-choke-point mechanism verbatim in spirit: importing that module swaps
``ExecCtx.take_decision`` for its recording wrapper (the same hook that built
``puzzle_corpus.json``); THIS module then wraps that wrapper one layer
outward to snapshot a minimal observation at the ask moment and to mirror
the ask order. Gold ordinals come from ``puzzle_cert.extract_items`` itself,
so the scripted-lane judgement (``_scripted_for_step``) is REUSED, not
re-derived — extraction order is identical in both layers because both count
every ``take_decision`` call in call order.

The observation is the design §1 "obs_tokens" surface, minimal by intent
(batch 1 validates the schema + loop, it is not the final featurizer):
turn, lives, active seat, acting seat, source card name, per-seat
battlefield name lists, hand sizes and mana pools (omniscient-v1 — the
masked C2 view is a drop-in deletion of the hidden fields, same schema).

Run::

    .venv/bin/python -m tools.training.packrec --out tools/training/episodes.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Import AFTER the direct imports: this installs puzzle_cert's
# take_decision / run_step hooks (its module-level patch). Our wrapper below
# then chains OUTWARD on top of the already-patched attribute.
import tools.audit.puzzle_cert as pcert
from MTG_bot.core.executor.games import get_supply
from MTG_bot.core.executor.quantity import ExecCtx
from MTG_bot.core.state import ZONE_BATTLEFIELD

#: rows of the episode currently being recorded (None = hook idle)
_records: list[dict[str, Any]] | None = None

#: puzzle_cert's patched take_decision (the inner layer of the chain)
_cert_take = ExecCtx.take_decision


def _obs_snapshot(ctx: ExecCtx) -> dict[str, Any]:
    """Minimal visible-state summary at the ask moment (design 09 §1).

    Read-only, defensive: an unreadable field degrades to ``None``/empty
    rather than breaking the replay — the gold line must run byte-identical
    whether or not the featurizer can see a lane."""
    world = getattr(ctx, "world", None)
    obs: dict[str, Any] = {
        "turn": None,
        "lives": [],
        "active": None,
        "seat": None,
        "source": [],
        "battlefield": [],
        "hand": [],
        "graveyard": [],
        "mana": [],
    }
    if world is None:  # bare unit-test ctx without a world
        return obs
    try:
        order = list(world.player_order)
        seats = {h: i for i, h in enumerate(order)}
        obs["turn"] = int(world.turn)
        obs["lives"] = [world.players[h].life for h in order]
        act = getattr(world, "active_player", None)
        obs["active"] = seats.get(act)
        obs["seat"] = seats.get(getattr(ctx, "controller", None))

        def card_row(handle: Any) -> list[str]:
            """Handle-canonical card row: the SAME handle token the
            candidate vocab uses, plus name and tapped/counters state —
            this is what lets the pointer scorer bind a candidate handle to
            the permanent it names (design 09 §1: permanents as Handle
            tokens x {tapped, counters, ...})."""
            state = world.cards[handle]
            row = [str(handle), str(state.identity.name)]
            if state.tapped:
                row.append("tapped")
            for k, v in sorted(state.counters.items()):
                row.append(f"{k}={v}")
            return row

        src = getattr(ctx, "source", None)
        if src is not None and src in world.cards:
            obs["source"] = card_row(src)
        for h in order:
            player = world.players[h]
            bf = player.zones.get(ZONE_BATTLEFIELD)
            obs["battlefield"].append(
                [card_row(c) for c in sorted(bf.entries, key=str)]
                if bf is not None
                else []
            )
            hand = player.zones.get("hand")
            obs["hand"].append(
                [card_row(c) for c in sorted(hand.entries, key=str)]
                if hand is not None
                else []
            )
            gy = player.zones.get("graveyard")
            obs.setdefault("graveyard", []).append(len(gy.entries) if gy else 0)
            pool = getattr(player, "mana_pool", None)
            obs["mana"].append(dict(sorted(pool.items())) if pool else {})
    except Exception as exc:  # noqa: BLE001 - degrade, never derail the replay
        obs["obs_error"] = f"{type(exc).__name__}: {exc}"
    return obs


def _take_recorded(self: ExecCtx, vocab: tuple, what: str) -> str:
    """Outer hook: snapshot obs BEFORE the decision, delegate to the
    puzzle_cert chain (which handles recorder/policy lanes), mirror the row."""
    if _records is None:
        return _cert_take(self, vocab, what)
    obs = _obs_snapshot(self)
    answer = _cert_take(self, vocab, what)
    _records.append(
        {
            "ordinal": len(_records),
            "what": what,
            "candidates": [str(v) for v in vocab],
            "answer": str(answer),
            "obs": obs,
        }
    )
    return answer


if ExecCtx.take_decision is not _take_recorded:
    ExecCtx.take_decision = _take_recorded  # type: ignore[method-assign]


def _gold_ordinals(pack: dict, rec: list[Any], runner: Any) -> list[int]:
    """Positions (in ask order) of the scripted-lane asks of one replay.

    Reuses puzzle_cert's ``_scripted_for_step`` lane-mirror; ordinals are
    resolved by IDENTITY (``is``), not ``AskRec.__eq__`` — a pack may ask the
    identical question twice in one step and equality-based indexing (the
    ``rec.index`` in ``extract_items``) would collapse such a pair."""
    by_step: dict[int, list[Any]] = {}
    for r in rec:
        by_step.setdefault(r.step, []).append(r)
    pos = {id(r): i for i, r in enumerate(rec)}
    out: list[int] = []
    for i, step in enumerate(pack["steps"]):
        for r, _word in pcert._scripted_for_step(
            step, by_step.get(i, []), runner.handles
        ):
            out.append(pos[id(r)])
    return sorted(out)


def record_pack(path: Path, supply: Any) -> dict[str, Any] | None:
    """Replay one pack's gold line; return its episode (or None if the pack
    carries no scripted decisions or yields no menu ask = designation lane)."""
    pack = json.loads(path.read_text(encoding="utf-8"))
    if not any(s.get("decisions") for s in pack.get("steps", ())):
        return None
    global _records
    _records = []
    rec: list[Any] = []
    saved = pcert._recorder
    pcert._recorder = rec
    try:
        runner, _ok = pcert._drive(pack, supply)
    finally:
        pcert._recorder = saved
        rows, _records = _records, None
    if runner is None or not rec:
        return None
    if len(rows) != len(rec):  # the two hooks must see the identical ask order
        raise AssertionError(
            f"{path.name}: obs hook saw {len(rows)} asks, cert {len(rec)}"
        )
    gold = set(_gold_ordinals(pack, rec, runner))
    for row in rows:
        row["gold"] = row["ordinal"] in gold
        if row["gold"]:
            row["gold_idx"] = row["candidates"].index(row["answer"])
    if not gold:
        return None
    card = next(
        (
            c.get("real") or c.get("name")
            for c in pack.get("cards", [])
            if c.get("real") or c.get("name")
        ),
        path.stem,
    )
    return {
        "pack": path.name,
        "card": card,
        "asks": rows,
        "gold_ordinals": sorted(gold),
    }


def record_dir(packs_dir: Path, supply: Any) -> list[dict[str, Any]]:
    """Record every decision-bearing pack, name-sorted (deterministic)."""
    episodes: list[dict[str, Any]] = []
    for p in sorted(packs_dir.glob("*.json")):
        try:
            ep = record_pack(p, supply)
        except Exception as exc:  # noqa: BLE001 - a broken pack is skipped, logged
            print(f"SKIP {p.name}: {type(exc).__name__}: {exc}")
            continue
        if ep is not None:
            episodes.append(ep)
    return episodes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--dir", default=str(REPO / "tools" / "scenarios"))
    ap.add_argument(
        "--out", default=str(REPO / "tools" / "training" / "episodes.jsonl")
    )
    args = ap.parse_args(argv)
    supply = get_supply("all")
    episodes = record_dir(Path(args.dir), supply)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for ep in episodes:
            fh.write(json.dumps(ep, sort_keys=True) + "\n")
    asks = sum(len(ep["asks"]) for ep in episodes)
    gold = sum(sum(1 for r in ep["asks"] if r["gold"]) for ep in episodes)
    print(f"episodes={len(episodes)} asks={asks} gold_lines={gold} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
