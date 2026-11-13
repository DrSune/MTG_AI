"""Blast radius of the five M20 fault fixes over the 19 sets, by script.

    .venv/bin/python reports/m20_faults_2026-11-12/blast_radius.py dump ROOT OUT.json
    .venv/bin/python reports/m20_faults_2026-11-12/blast_radius.py compare BASE.json HEAD.json

``dump`` compiles every set with the code under ROOT (first on sys.path) as games deal it (card
records applied, verified ones only) and as the card tools see it (every record applied), and
writes each card's tree hash, each set's verified and compiled pools, and the verified cards whose
play the fixes can change with their bytes unchanged:
- ``any_number``: an effect-role CHOOSE over an unbounded count ("any number of", CR 107.1c),
  asked now instead of taking every candidate (faults 1 and 2);
- ``hand_put``: a move from a hand to anywhere but a graveyard, asked as a choice now, not a
  discard (fault 5);
- ``all_window``: an ALL selector over the top of a library, the looked-at cards now (fault 3);
- ``emblem``: a GET_EMBLEM (fault 4: every emblem its own object, CR 114.2);
- ``nested_target``: a spell's or an activated ability's effect holding another ability (granted,
  a token's, an emblem's, a delayed trigger) that designates: its targets are its own now, not
  the outer ability's (query.activation_target_slots, spell_target_slots).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def dump(root: Path, out: Path) -> None:
    sys.path.insert(0, str(root))
    sys.path.insert(1, str(root / "tools" / "cards"))
    import corpus

    from MTG_bot.core import ability_tree
    from MTG_bot.core.ability_tree import (
        Atom,
        BackFace,
        QUnbounded,
        Selector,
        SelectorMode,
        Verb,
        Zone,
        ZoneKind,
        ZonePosition,
        walk,
    )
    from MTG_bot.core.compiler.card_records import tree_sha
    from MTG_bot.core.executor.games import compile_supply

    assert Path(sys.modules["MTG_bot"].__file__).resolve().is_relative_to(root.resolve())

    foreign = (*ability_tree._A_CLASSES, ability_tree.TokenSpec, ability_tree.DelayedTrigger,
               *(t for t in (getattr(ability_tree, "EmblemSpec", None),) if t is not None))

    def designates(node) -> bool:
        for inner in walk(node):
            if not isinstance(inner, Atom):
                continue
            for _role, value in inner.args.pairs:
                if isinstance(value, Selector) and value.mode is SelectorMode.TARGET and value.referent is None:
                    return True
                if isinstance(value, ability_tree.ControllerRef) and value in ability_tree.DESIGNATED_PLAYER_REFS:
                    return True
        return False

    def flags(card) -> list[str]:
        found = set()
        for ability in card.abilities:
            effect = getattr(ability, "effect", None)
            if isinstance(ability, (ability_tree.ActivatedAbility, ability_tree.SpellAbility)) and effect is not None:
                if any(n is not effect and isinstance(n, foreign) and designates(n) for n in walk(effect)):
                    found.add("nested_target")
        for node in walk(card, skip=BackFace):
            if not isinstance(node, Atom):
                continue
            if node.verb is Verb.GET_EMBLEM:
                found.add("emblem")
            frm, dest = node.args.get("from"), node.args.get("destination")
            if (node.verb is Verb.MOVE_ZONE and isinstance(frm, Zone) and frm.kind is ZoneKind.HAND
                    and isinstance(dest, Zone) and dest.kind is not ZoneKind.GRAVEYARD):
                found.add("hand_put")
            for role, value in node.args.pairs:
                if not isinstance(value, Selector):
                    continue
                if (value.mode is SelectorMode.CHOOSE and isinstance(value.count, QUnbounded)
                        and not (node.verb is Verb.CAST and role == "source")):
                    found.add("any_number")
                if value.mode is SelectorMode.ALL and any(
                    z.kind is ZoneKind.LIBRARY and z.position is ZonePosition.TOP for z in value.zones
                ):
                    found.add("all_window")
        return sorted(found)

    report: dict = {}
    for code in corpus.SETS:
        games = compile_supply("all", code)
        tools = compile_supply("all", code, require_verified=False)
        verified = sorted(games.verified_ids)
        # the "compiled" pool mode (games.compile_supply): castable, nothing unparsed
        compiled = sorted(
            oid for oid in games.playable_engine_ids
            if not (games.pool.results[oid].unparsed or games.pool.results[oid].ambiguities
                    or games.pool.results[oid].back_face_unparsed)
        )
        names = {oid: res.card.name for oid, res in games.pool.results.items()}
        entry = {
            # a card's tree: its keywords, abilities and P/T (card_records.tree_sha), not the whole
            # record, whose bytes lost the removed CardRecord.emblem key on every card
            "trees": {oid: tree_sha(res.card) for oid, res in games.pool.results.items()},
            "trees_mapped": {oid: tree_sha(res.card) for oid, res in tools.pool.results.items()},
            "verified": verified,
            "compiled": compiled,
            "names": names,
            "flags": {},
        }
        for oid in verified:
            hit = flags(games.pool.results[oid].card)
            if hit:
                entry["flags"][names[oid]] = hit
        report[code] = entry
        print(code, len(verified), len(compiled), file=sys.stderr, flush=True)
    out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")


def compare(base_path: Path, head_path: Path) -> None:
    base = json.loads(base_path.read_text())
    head = json.loads(head_path.read_text())
    summary: dict = {}
    total = changed_total = 0
    for code in head:
        b, h = base[code], head[code]
        names = {**b["names"], **h["names"]}
        oids = set(b["trees"]) | set(h["trees"])
        total += len(oids)
        changed = sorted(names.get(o, o) for o in oids if b["trees"].get(o) != h["trees"].get(o))
        changed_total += len(changed)
        mapped = sorted(names.get(o, o) for o in set(b["trees_mapped"]) | set(h["trees_mapped"])
                        if b["trees_mapped"].get(o) != h["trees_mapped"].get(o))
        summary[code] = {
            "trees_changed": changed,
            "trees_changed_with_every_record": mapped,
            "verified": [len(b["verified"]), len(h["verified"])],
            "verified_left": sorted(names.get(o, o) for o in set(b["verified"]) - set(h["verified"])),
            "verified_joined": sorted(names.get(o, o) for o in set(h["verified"]) - set(b["verified"])),
            "compiled": [len(b["compiled"]), len(h["compiled"])],
            "compiled_left": sorted(names.get(o, o) for o in set(b["compiled"]) - set(h["compiled"])),
            "compiled_joined": sorted(names.get(o, o) for o in set(h["compiled"]) - set(b["compiled"])),
            "verified_flagged_unchanged_bytes": {
                n: f for n, f in h["flags"].items()
                if n not in changed
            },
        }
    summary["_totals"] = {"cards": total, "trees_changed": changed_total}
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "dump":
        dump(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        compare(Path(sys.argv[2]), Path(sys.argv[3]))
