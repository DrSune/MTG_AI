"""Census for engine wave E3 (faults 1 and 2): over the 19 sets' trees, records applied (verified or
not), every place a battlefield zone is scoped to a player, every SacrificeEvent actor, and every
PUT_COUNTER by how it names its recipient.

    census.py <checkout> <out.txt>
"""
from __future__ import annotations

import dataclasses
import sys
from collections import Counter, defaultdict
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
PLAYER_FREE = (at.ControllerRef.ANY, at.ControllerRef.OWNER)


def paths(node, path=()):
    """(path, node) for every dataclass node; path = tuple of (class name, field[, index])."""
    yield path, node
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        for f in dataclasses.fields(node):
            yield from _value(getattr(node, f.name), path + ((type(node).__name__, f.name),))


def _value(v, path):
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        yield from paths(v, path)
    elif isinstance(v, (tuple, frozenset)):
        for i, item in enumerate(v):
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str):
                yield from _value(item[1], path + (("role", item[0]),))  # an AtomArgs pair
            else:
                yield from _value(item, path)


def bf_player(zone) -> bool:
    return isinstance(zone, at.Zone) and zone.kind is at.ZoneKind.BATTLEFIELD and zone.controller not in PLAYER_FREE


rows: dict[str, list[str]] = defaultdict(list)
counts: Counter = Counter()
registry = build_full_registry()
for code in SETS:
    raw = ingest_pool(ROOT / "MTG_bot" / "data" / f"{code}.json")
    records = card_records.load_records(code)
    for oid, rc in raw.items():
        if rc.is_token or rc.is_emblem:
            continue
        try:
            res = compile_pool({oid: rc}, registry, records=records, require_verified=False).results[oid]
        except (StateCorruptionError, ValueError):
            continue
        ver = "VERIFIED" if card_records.is_verified(res, records.get(oid)) else "-"
        name = rc.identity.name
        tag = f"{code} | {name} | {ver}"
        for path, n in paths(res.card):
            kinds = [cls for cls, _f in path]
            outer = next((k for k in reversed(kinds) if k in (
                "TriggeredAbility", "ActivatedAbility", "StaticAbility", "SpellAbility",
                "ReplacementAbility", "EtBState", "DelayedTrigger", "TokenSpec", "EmblemSpec",
                "CostModifier", "Keyword", "KeywordAbility")), "?")
            if isinstance(n, at.ZoneChangeEvent):
                ends = [(e, z) for e, z in (("from", n.from_zone), ("to", n.to_zone)) if bf_player(z)]
                if ends:
                    selfish = isinstance(n.subject, at.FAtom) and n.subject.pred is at.FAtomPred.IS_SOURCE
                    for e, z in ends:
                        counts[f"ZCE {e} {z.controller.name} self={selfish} {outer}"] += 1
                        rows[f"ZCE {e}"].append(f"{tag} | {outer} | {e}={z.controller.name} | self={selfish}")
            if isinstance(n, at.SacrificeEvent) and n.actor is not None:
                rows["SAC actor"].append(f"{tag} | {outer} | actor={n.actor!r:.120}")
            if isinstance(n, at.FAtom):
                for attr in ("from_zone", "to_zone", "zone"):
                    z = getattr(n, attr, None)
                    if bf_player(z):
                        rows["FATOM bf zone"].append(f"{tag} | {outer} | {n.pred.name}.{attr}={z.controller.name} | who={getattr(n, 'who', None)}")
            if isinstance(n, at.Selector) and any(bf_player(z) for z in n.zones):
                role = next((f for cls, f in reversed(path) if cls == "role"), "?")
                verb = next((c for c, f in reversed(path) if c == "Atom"), None)
                rows["SEL bf zone"].append(f"{tag} | {outer} | role={role} | mode={n.mode.name} | zones={[ (z.kind.name, z.controller.name) for z in n.zones]} | path={'/'.join(c + '.' + f for c, f in path[-4:])}")
            if isinstance(n, at.Atom) and n.verb is at.Verb.MOVE_ZONE:
                d = n.args.get("destination")
                if bf_player(d):
                    counts[f"DEST bf {d.controller.name}"] += 1
            if isinstance(n, at.EtBState) and (n.condition is not None or n.initial_counters):
                rows["ETBSTATE"].append(f"{tag} | cond={n.condition!r:.100} | counters={n.initial_counters!r:.100}")
            if isinstance(n, at.Atom) and outer in ("TriggeredAbility", "ActivatedAbility", "DelayedTrigger"):
                for role, val in n.args.pairs:
                    if isinstance(val, at.Selector) and (
                            val.referent == "source"
                            or val.referent is None and isinstance(val.filter, at.FAtom)
                            and val.filter.pred is at.FAtomPred.IS_SOURCE):
                        counts[f"ACTS-ON-SOURCE {n.verb.name}.{role} {outer}"] += 1
                        rows[f"ACTS-ON-SOURCE {n.verb.name}.{role}"].append(f"{tag} | {outer} | {'referent' if val.referent else 'self-' + val.mode.name}")
            if isinstance(n, at.Atom) and n.verb is at.Verb.PUT_COUNTER:
                t = n.args.get("target")
                how = "?"
                if isinstance(t, at.Selector):
                    if t.referent is not None:
                        how = f"referent={t.referent}"
                    elif isinstance(t.filter, at.FAtom) and t.filter.pred is at.FAtomPred.IS_SOURCE:
                        how = f"self-{t.mode.name}"
                    else:
                        how = f"{t.mode.name} zones={[(z.kind.name, z.controller.name) for z in t.zones]}"
                counts[f"PUT_COUNTER {how} {outer} {ver}"] += 1
                if how.startswith(("referent=source", "self-")):
                    rows[f"PUT_COUNTER on source ({outer})"].append(f"{tag}")
                if "GRAVEYARD" in how or "EXILE" in how or "ANY" in how and "BATTLEFIELD" not in how:
                    rows["PUT_COUNTER off the battlefield"].append(f"{tag} | {outer} | {how}")
    print(code, file=sys.stderr)

with open(sys.argv[2], "w") as out:
    for k, v in sorted(counts.items()):
        print(f"{v:5d}  {k}", file=out)
    for key, lines in sorted(rows.items()):
        print(f"\n== {key}: {len(lines)}", file=out)
        for line in sorted(lines):
            print("  " + line, file=out)
