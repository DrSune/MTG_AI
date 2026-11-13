"""Which verified cards (M21, M20, FDN) read an engine path the one-event change touched, by the
facts of their trees (records applied, as dealt):

- lookback: a trigger that looks back (CR 603.10a: a death, a sacrifice, a zone change from the
  battlefield or a graveyard): it now sees the other objects one event moved off at once;
- enters-other: a zone-change trigger into the battlefield over another object: it now sees the
  newcomers of its own event (CR 603.6a);
- layer-read: a trigger that does not look back whose event filter reads a characteristic a
  continuous effect can change (keyword, type, power/toughness, a chosen creature type): read now
  with the layers brought up to date (CR 603.10);
- granted-trigger: a static that grants a triggered ability (granted look-back triggers read the
  departed host's last known abilities);
- event-act: a per-object trigger acting on Selector(referent="event") ("it"): no longer acts on
  an object that changed zones since (CR 400.7);
- event-info: a QProp of the event referent or a player read through it (CR 608.2h: by last
  known information);
- eachplayer-move: an EachPlayer whose effect moves objects (one event, CR 101.4);
- replacement: a replacement ability (its action shares the event it modified, CR 614.6);
- gy-only: the binder's CR 113.6m classifier files a trigger as graveyard-only (on this checkout).

    reach.py <checkout> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__

from MTG_bot.core import ability_tree as at
from MTG_bot.core.executor.binding import functions_from_graveyard
from MTG_bot.core.executor.games import get_supply

LAYER_PREDS = {at.FAtomPred.KEYWORD_HAS, at.FAtomPred.TYPE_EQ, at.FAtomPred.SUBTYPE_EQ,
               at.FAtomPred.SUPERTYPE_EQ, at.FAtomPred.POWER_GE, at.FAtomPred.POWER_LE,
               at.FAtomPred.PT_LE, at.FAtomPred.NAME_CHOSEN}
MOVERS = {at.Verb.MOVE_ZONE, at.Verb.SACRIFICE, at.Verb.DESTROY, at.Verb.CREATE_TOKEN}


def looks_back(ev) -> bool:
    if isinstance(ev, (at.CreatureDiesEvent, at.SacrificeEvent)):
        return True
    return isinstance(ev, at.ZoneChangeEvent) and (
        ev.from_zone.kind in (at.ZoneKind.BATTLEFIELD, at.ZoneKind.GRAVEYARD)
        or ev.to_zone.kind in (at.ZoneKind.HAND, at.ZoneKind.LIBRARY))


def self_only(subject) -> bool:
    parts = subject.children if isinstance(subject, at.FAnd) else (subject,)
    return any(isinstance(p, at.FAtom) and p.pred is at.FAtomPred.IS_SOURCE for p in parts)


def facts(card) -> list[str]:
    out = set()
    for n in at.walk(card):
        if isinstance(n, (at.TriggeredAbility, at.DelayedTrigger)) and n.event is not None:
            ev = n.event
            if looks_back(ev):
                out.add("lookback")
            elif isinstance(ev, at.ZoneChangeEvent) and ev.to_zone.kind is at.ZoneKind.BATTLEFIELD \
                    and (ev.subject is None or not self_only(ev.subject)):
                out.add("enters-other")
            if not looks_back(ev) and {m.pred for m in at.walk(ev) if isinstance(m, at.FAtom)} & LAYER_PREDS:
                out.add("layer-read")
            gathered = at.gathers_objects(ev, n.once_per_event)
            for m in at.walk(n.effect) if n.effect is not None else ():
                if isinstance(m, at.Atom):
                    for _role, v in m.args.pairs:
                        if isinstance(v, at.Selector) and v.referent == "event" and not gathered:
                            out.add("event-act")
                if isinstance(m, at.QProp) and m.referent == "event" and m.field not in (
                        at.QPropField.AMOUNT, at.QPropField.THAT_MANY_COUNT, at.QPropField.THIS_WAY_COUNT):
                    out.add("event-info")
        if isinstance(n, at.Atom) and n.verb is at.Verb.GRANT_ABILITY and isinstance(
                n.args.get("ability"), at.TriggeredAbility):
            out.add("granted-trigger")
        if isinstance(n, at.EachPlayer) and any(isinstance(m, at.Atom) and m.verb in MOVERS
                                                 for m in at.walk(n.effect)):
            out.add("eachplayer-move")
        if isinstance(n, at.ReplacementAbility):
            out.add("replacement")
    if any(functions_from_graveyard(ab) for ab in card.abilities):
        out.add("gy-only")
    return sorted(out)


dump = {}
for code in ("M21", "M20", "FDN"):
    sup = get_supply("verified", code)
    dump[code] = {sup.pool.results[oid].card.name: facts(sup.pool.results[oid].card)
                  for oid in sup.deckable}
Path(sys.argv[2]).write_text(json.dumps(dump, indent=0, sort_keys=True))
for code, cards in dump.items():
    counts = {}
    for f in cards.values():
        for x in f:
            counts[x] = counts.get(x, 0) + 1
    print(code, len(cards), "verified deckable;", dict(sorted(counts.items())), file=sys.stderr)
