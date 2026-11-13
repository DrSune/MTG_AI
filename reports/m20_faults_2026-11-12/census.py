"""The class of each of the five M20 faults over the 19 sets, by script: oracle text and compiled
trees (every card record applied, as the card tools see them).

    .venv/bin/python reports/m20_faults_2026-11-12/census.py ROOT OUT.json

- ``any_number``: effect-role CHOOSE selectors over an unbounded count (Battalion Foot Soldier,
  Cavalier of Flame), and every sentence printing "any number of";
- ``all_revealed``: sentences putting "all ... revealed this way" somewhere, and the trees whose
  library-top partition picks more than one card (ONE_OF of a count above 1; ALL over the top);
- ``emblems``: the emblem entries of the 19 sets, every sentence that makes one, and the trees that
  carry a GET_EMBLEM (with its recipient, and whether its emblem has abilities);
- ``hand_moves``: MOVE_ZONE from a hand by destination (Cavalier of Gales's "put two cards from
  your hand on top of your library"), and the sentences that put cards from a hand elsewhere;
- ``nested_designations``: abilities whose effect carries another ability (granted, a token's, an
  emblem's, a delayed trigger) that designates a target or a player.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
sys.path.insert(1, str(root / "tools" / "cards"))
import corpus  # noqa: E402

from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.ability_tree import Atom, QConst, QUnbounded, Selector, SelectorMode, Verb, Zone, ZoneKind, walk  # noqa: E402
from MTG_bot.core.compiler import card_records  # noqa: E402

FOREIGN = (*at._A_CLASSES, at.TokenSpec, at.DelayedTrigger,
           *(t for t in (getattr(at, "EmblemSpec", None),) if t is not None))


def designates(node) -> bool:
    for inner in walk(node):
        if isinstance(inner, Atom):
            for _role, value in inner.args.pairs:
                if isinstance(value, Selector) and value.mode is SelectorMode.TARGET and value.referent is None:
                    return True
                if isinstance(value, at.ControllerRef) and value in at.DESIGNATED_PLAYER_REFS:
                    return True
    return False


out: dict = {k: {"trees": [], "text": []} for k in ("any_number", "all_revealed", "hand_moves")}
out["emblems"] = {"entries": [], "text": [], "trees": []}
out["nested_designations"] = []
for code in corpus.SETS:
    sc = corpus.compile_set(code)
    for oid, raw in sc.raw.items():
        name = raw.identity.name
        if raw.is_emblem:
            out["emblems"]["entries"].append([code, name, raw.identity.oracle_text])
            continue
        res = sc.results.get(oid)
        tag = [code, name, "verified" if res and card_records.is_verified(res, sc.records.get(oid)) else
               "mapped" if "ir" in sc.records.get(oid, {}) else "compiled" if res else "refused"]
        unparsed = {s for s, _ in res.unparsed} | {s for s, _ in res.back_face_unparsed} if res else set()
        sentences = [*raw.sentences, *(raw.back_face.sentences if raw.back_face else ())]
        for s in sentences:
            low = re.sub(r"\([^)]*\)", "", s).lower()  # reminder text left out
            row = [*tag, s, "unparsed" if s in unparsed or res is None else "parsed"]
            if "any number of" in low:
                out["any_number"]["text"].append(row)
            if re.search(r"\ball\b.*\brevealed this way\b", low):
                out["all_revealed"]["text"].append(row)
            if "an emblem with" in low:
                out["emblems"]["text"].append(row)
            if re.search(r"cards? from (your|their) hand (on|onto|into)", low):
                out["hand_moves"]["text"].append(row)
        if res is None:
            continue
        for ability in res.card.abilities:
            effect = getattr(ability, "effect", None)
            if effect is not None and any(
                n is not effect and isinstance(n, FOREIGN) and designates(n) for n in walk(effect)
            ):
                out["nested_designations"].append([*tag, type(ability).__name__])
        for node in walk(res.card):
            if not isinstance(node, Atom):
                continue
            if node.verb is Verb.GET_EMBLEM:
                emblem = node.args.get("emblem")
                who = node.args.get("controller")
                out["emblems"]["trees"].append([*tag, getattr(who, "name", None),
                                                len(emblem.abilities) if emblem is not None else 0])
            frm, dest = node.args.get("from"), node.args.get("destination")
            if node.verb is Verb.MOVE_ZONE and isinstance(frm, Zone) and frm.kind is ZoneKind.HAND:
                sel = node.args.get("cards")
                out["hand_moves"]["trees"].append([*tag, dest.kind.name, getattr(sel, "mode", None) and sel.mode.name])
            for role, value in node.args.pairs:
                if not isinstance(value, Selector):
                    continue
                if value.mode is SelectorMode.CHOOSE and isinstance(value.count, QUnbounded):
                    out["any_number"]["trees"].append([*tag, node.verb.name, role])
                top = any(z.kind is ZoneKind.LIBRARY and z.position is at.ZonePosition.TOP for z in value.zones)
                if top and (value.mode is SelectorMode.ALL or (
                        value.mode is SelectorMode.ONE_OF and not (isinstance(value.count, QConst) and value.count.value == 1))):
                    out["all_revealed"]["trees"].append([*tag, node.verb.name, value.mode.name, repr(value.count)])
Path(sys.argv[2]).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
print(json.dumps({k: {kk: len(vv) for kk, vv in v.items()} if isinstance(v, dict) else len(v) for k, v in out.items()}))
