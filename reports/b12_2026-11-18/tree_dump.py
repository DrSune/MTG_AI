"""Per checkout: every card of the 19 sets with its compiler tree sha, its tree with card records
applied (verified or not), whether that tree is the verified one, and the facts round B12's
engine changes read (DESIGN_ATOM_ONTOLOGY §19). Run from each checkout; diff the two JSON files
with tree_diff.py (round 13's, unchanged).

    tree_dump.py <checkout> <out.json>

Facts (read on a card's tree with records applied):
- lose-game / win-game: LOSE_GAME, WIN_GAME (verbs._v_lose_game, _v_win_game);
- opening-hand: the opening-hand action (games.opening_hand_actions);
- prevent-<event>: a PREVENT_EFFECT over a CastSpellEvent, ZoneChangeEvent, LifeGainedEvent or
  GameOutcomeEvent (the round's new prevention consumers), and every other PREVENT_EFFECT
  ("prevent-other": the registry it shares);
- gain-life / cast / enter: a GAIN_LIFE or a lifelink keyword (the life-gain lane), a CAST or a
  PERMIT (the cast lanes), a move onto the battlefield (the enter lane).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__

from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.compiler import card_records  # noqa: E402
from MTG_bot.core.compiler.compiler import compile_pool  # noqa: E402
from MTG_bot.core.compiler.coverage import build_full_registry  # noqa: E402
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402
from MTG_bot.core.errors import StateCorruptionError  # noqa: E402

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
WIN = getattr(at.Verb, "WIN_GAME", None)
OUTCOME = getattr(at, "GameOutcomeEvent", None)
OPENING = getattr(at, "OpeningHandAbility", None)


def facts(card) -> list[str]:
    out = set()
    for n in at.walk(card):
        if OPENING is not None and isinstance(n, OPENING):
            out.add("opening-hand")
        if isinstance(n, at.KeywordAbility) and n.keyword is at.Keyword.LIFELINK:
            out.add("gain-life")
        if not isinstance(n, at.Atom):
            continue
        if n.verb is at.Verb.LOSE_GAME:
            out.add("lose-game")
        elif WIN is not None and n.verb is WIN:
            out.add("win-game")
        elif n.verb is at.Verb.GAIN_LIFE:
            out.add("gain-life")
        elif n.verb in (at.Verb.CAST, at.Verb.PERMIT):
            out.add("cast")
        elif n.verb in (at.Verb.MOVE_ZONE, at.Verb.SEARCH):
            dest = n.args.get("destination")
            if isinstance(dest, at.Zone) and dest.kind is at.ZoneKind.BATTLEFIELD:
                out.add("enter")
        elif n.verb is at.Verb.PREVENT_EFFECT:
            event = n.args.get("event")
            kinds = (at.CastSpellEvent, at.ZoneChangeEvent, at.LifeGainedEvent) + (
                (OUTCOME,) if OUTCOME is not None else ())
            name = type(event).__name__
            out.add(f"prevent-{name}" if isinstance(event, kinds) else "prevent-other")
    return sorted(out)


def compiled(oid, rc, records=None):
    """The card's compile result (records applied when given, verified or not), or why the
    compiler refused it."""
    try:
        return compile_pool({oid: rc}, registry, records=records, require_verified=False).results[oid]
    except (StateCorruptionError, ValueError) as exc:
        return f"refused: {type(exc).__name__}: {str(exc)[:160]}"


registry = build_full_registry()
dump: dict = {}
for code in SETS:
    raw = ingest_pool(ROOT / "MTG_bot" / "data" / f"{code}.json")
    records = card_records.load_records(code)
    rows = {}
    for oid, rc in raw.items():
        if rc.is_token or rc.is_emblem:
            continue
        comp = compiled(oid, rc)
        rec = compiled(oid, rc, records)
        row = {"name": rc.identity.name}
        row["compiler"] = card_records.tree_sha(comp.card) if not isinstance(comp, str) else comp
        if not isinstance(comp, str):
            row["compiler_unparsed"] = len(comp.unparsed) + len(comp.back_face_unparsed)
        if not isinstance(rec, str):
            row["tree"] = card_records.tree_sha(rec.card)
            row["record"] = rec.record is not None
            row["verified"] = card_records.is_verified(rec, records.get(oid))
            row["facts"] = facts(rec.card)
            row["unparsed"] = len(rec.unparsed) + len(rec.back_face_unparsed)
            row["needs_atom"] = bool(records.get(oid, {}).get("needs_atom"))
        else:
            row["tree"] = rec
        rows[oid] = row
    dump[code] = rows
    print(code, len(rows), file=sys.stderr)
Path(sys.argv[2]).write_text(json.dumps(dump, indent=0, sort_keys=True))
