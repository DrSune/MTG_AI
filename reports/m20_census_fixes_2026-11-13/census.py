"""The classes of the four fixes and the two analyses (2026-11-13), over the 19 sets: printed
wordings by regex (unique names) and, with card records applied (verified or not), the trees that
read each changed engine path.

    census.py <checkout>
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
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

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
REMINDER = re.compile(r"\([^)]*\)")
TEXT = {
    "1 player hexproof (printed)": r"(you have hexproof|you and permanents you control gain hexproof"
                                   r"|you, planeswalkers you control, and other creatures you control have hexproof)",
    "2 an actor named through an 'up to' target": r"up to (one|two|three|x|\w+) (other )?target[^.]*\.[^.]*\b"
                                                  r"(its controller|that player|that creature's controller)",
    "3 a triggered sentence with two 'target' words": None,  # by sentence, below
    "4 reveal ... until": r"reveals? cards from the top of [^.]* library until",
    "5a damage to a referent's controller": r"damage to (that creature's|that spell's|that permanent's|its|that land's"
                                            r"|that artifact's|that planeswalker's) controller",
    "5b a discard trigger": r"whenever (you|a player|an opponent|one or more players?) discards?",
    "5b a replacement that sends a discard elsewhere": r"would be put into (a|an opponent's|your|their|any) "
                                                       r"graveyard from anywhere",
}
registry = build_full_registry()
text_hits: dict[str, dict[str, list[str]]] = defaultdict(dict)
paths: dict[str, list[str]] = defaultdict(list)
FOREIGN = (*at._A_CLASSES, at.TokenSpec, at.DelayedTrigger)
ABILITIES = (at.SpellAbility, at.ActivatedAbility, at.TriggeredAbility, at.DelayedTrigger, at.StaticAbility)
for code in SETS:
    raw = ingest_pool(ROOT / "MTG_bot" / "data" / f"{code}.json")
    records = card_records.load_records(code)
    for oid, rc in raw.items():
        if rc.is_token or rc.is_emblem:
            continue
        name = rc.identity.name
        text = " ".join(rc.sentences)
        for label, pat in TEXT.items():
            if pat is not None and re.search(pat, text, re.I):
                text_hits[label].setdefault(name, []).append(code)
        for s in rc.sentences:
            body = REMINDER.sub("", s)
            if re.match(r"^(When|Whenever|At)\b", body) and len(re.findall(r"\btargets?\b", body)) >= 2:
                text_hits["3 a triggered sentence with two 'target' words"].setdefault(name, []).append(code)
        try:
            res = compile_pool({oid: rc}, registry, records=records, require_verified=False).results[oid]
        except Exception:  # noqa: BLE001 - a refused card reads no engine path
            continue
        tag = f"{code} {name}" + (" (verified)" if card_records.is_verified(res, records.get(oid)) else "")
        for top in res.card.abilities:
            for ab in at.walk(top):
                if not isinstance(ab, ABILITIES) or getattr(ab, "effect", None) is None:
                    continue
                own = [n for n in at.walk(ab.effect, skip=FOREIGN) if not isinstance(n, FOREIGN)]
                sels = {repr(n) for n in own if isinstance(n, at.Selector)
                        and n.mode is at.SelectorMode.TARGET and n.referent is None}
                player = any(v in at.DESIGNATED_PLAYER_REFS for n in own if not isinstance(n, at.Selector)
                             for v in at._leaf_values(n))
                if len(sels) + int(player) > 1 and not isinstance(ab, at.StaticAbility):
                    paths[f"3 {type(ab).__name__} with several designations"
                          + (" incl. a player" if player else "")].append(tag)
                for n in own:
                    if isinstance(n, at.Atom):
                        actor = n.args.get("controller")
                        if isinstance(actor, at.Selector) and actor.referent is not None:
                            paths["2 an atom whose acting player is a referent"].append(
                                f"{tag}: {n.verb.name} referent {actor.referent}")
                        if n.verb is at.Verb.REVEAL and n.args.get("until") is not None:
                            paths["4 a REVEAL until"].append(tag)
                        if n.verb is at.Verb.GRANT_ABILITY:
                            tgt = n.args.get("target")
                            if isinstance(tgt, at.Selector) and any(z.kind is at.ZoneKind.PLAYER for z in tgt.zones):
                                paths["1 a grant to a player"].append(
                                    f"{tag}: {n.args.get('ability').keyword.name}")
for label in sorted(TEXT):
    hits = text_hits.get(label, {})
    print(f"== {label}: {len(hits)} cards")
    for name, codes in sorted(hits.items()):
        print(f"   {name} {sorted(set(codes))}")
for label in sorted(paths):
    rows = sorted(set(paths[label]))
    print(f"== trees, {label}: {len(rows)}")
    for row in rows:
        print("  ", row)
