#!/usr/bin/env python3
"""Wave-1 target map: the golden-compiled IR of the ETB family (17a).

There is no vision model in this repo (the round-16 close-out note's
"vision pipeline" never landed — verified 2026-09-30). The audited
universe is therefore exactly what the goldens are: the 305 M21 cards,
every one of which has real Scryfall art on disk
(``MTG_bot/assets/card_images/<oracle_id>.jpg``) — the old "cards that
showed up in vision" filter is here the honest filter "card with art
asset + engine-supported + has an ETB trigger".

The IR is NOT hand-written: every row is read out of the compiled
golden pool (:func:`ingest_pool` + :func:`build_full_registry` +
:func:`compile_pool` — the same chain ``games.compile_supply`` runs),
so ``wave1.json`` is a measurement, and ``--lint`` re-measures and
diffs against the frozen file: a golden edit that changes the ETB
family, the verb set, or engine support flips lint to red.

Usage::

    .venv/bin/python tools/audit/wave_builder.py            # write wave1.json
    .venv/bin/python tools/audit/wave_builder.py --lint     # re-derive, diff

Exit code 0 = wave file current (lint) / written (build).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from MTG_bot.core.ability_tree import Atom, TriggeredAbility, ZoneChangeEvent, walk
from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.executor import SUPPORTED_VERBS_V2

DATA = REPO / "MTG_bot" / "data" / "M21.json"
ASSETS = REPO / "MTG_bot" / "assets" / "card_images"
DEFAULT_OUT = Path(__file__).resolve().parent / "wave1.json"


def is_battlefield(zone) -> bool:
    """Zone-vs-BATTLEFIELD test that survives Zone-enum vs constant forms."""
    kind = getattr(zone, "kind", zone)
    name = getattr(kind, "name", kind)
    return str(name).endswith("BATTLEFIELD")


def etb_triggers(record) -> list[TriggeredAbility]:
    """The family map: TriggeredAbility whose EVENT is a zone change INTO
    the battlefield (the T8-audit-corrected structured event, never a
    substring)."""
    return [
        t
        for t in walk(record)
        if isinstance(t, TriggeredAbility)
        and isinstance(t.event, ZoneChangeEvent)
        and is_battlefield(t.event.to_zone)
    ]


def printed_texts() -> dict[str, str]:
    """oracle_id -> rules text (the raw Scryfall set file keeps the human
    text; make_replay.card_text_map is the same derivation)."""
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for card in raw["data"]["cards"]:
        oid = (card.get("identifiers") or {}).get("scryfallOracleId")
        if not oid:
            continue
        out.setdefault(oid, card.get("text") or card.get("originalText") or "")
    return out


def derive_wave() -> dict:
    raw = ingest_pool(DATA)
    registry = build_full_registry()
    pool = compile_pool(raw, registry)
    gated = compile_pool(raw, registry, supported_verbs=set(SUPPORTED_VERBS_V2))
    texts = printed_texts()
    cards: dict[str, dict] = {}
    for oid, res in pool.results.items():
        record = res.card
        if record.is_token or oid in pool.emblems:
            continue
        ets = etb_triggers(record)
        if not ets:
            continue
        verbs = sorted(
            {v.verb.name for t in ets for v in walk(t.effect) if isinstance(v, Atom)}
        )
        cards[record.name] = {
            "oracle_id": oid,
            "mechanics": verbs,
            "n_etb_triggers": len(ets),
            "subject_narrowed": any(
                getattr(t.event, "subject", None) is not None for t in ets
            ),
            "engine_supported": bool(gated.results[oid].legality.engine_supported),
            "image": str(ASSETS / f"{oid}.jpg"),
            "has_image": (ASSETS / f"{oid}.jpg").exists(),
            "printed_text": texts.get(oid, ""),
        }
    return {
        "meta": {
            "wave": "wave1",
            "family": "ETB (ZoneChangeEvent to BATTLEFIELD)",
            "source": "golden pool: ingest_pool + build_full_registry + compile_pool",
            "built_by": "tools/audit/wave_builder.py",
            "n_cards": len(cards),
        },
        "cards": dict(sorted(cards.items())),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--lint", action="store_true", help="re-derive and diff vs disk")
    args = ap.parse_args(argv)

    wave = derive_wave()
    text = json.dumps(wave, indent=2, sort_keys=True) + "\n"

    if args.lint:
        disk = Path(args.out).read_text(encoding="utf-8")
        if disk == text:
            print(f"lint OK: {wave['meta']['n_cards']} cards, IR current")
            return 0
        old = json.loads(disk)
        gone = set(old["cards"]) - set(wave["cards"])
        new = set(wave["cards"]) - set(old["cards"])
        changed = [
            n
            for n in set(old["cards"]) & set(wave["cards"])
            if old["cards"][n] != wave["cards"][n]
        ]
        print(
            f"lint DRIFT: dropped={sorted(gone)} added={sorted(new)} "
            f"changed={sorted(changed)}"
        )
        return 1

    Path(args.out).write_text(text, encoding="utf-8")
    print(
        f"wrote {args.out}: {wave['meta']['n_cards']} ETB cards "
        f"({sum(c['engine_supported'] for c in wave['cards'].values())} "
        f"engine-supported, {sum(c['has_image'] for c in wave['cards'].values())} "
        f"with art)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
