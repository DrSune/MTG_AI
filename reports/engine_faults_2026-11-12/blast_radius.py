"""Blast radius of the three engine fixes over the 19 sets, by script.

    .venv/bin/python reports/engine_faults_2026-11-12/blast_radius.py dump ROOT OUT.json
    .venv/bin/python reports/engine_faults_2026-11-12/blast_radius.py compare BASE.json HEAD.json

``dump`` compiles every set with the code under ROOT (first on sys.path) as games deal it (card
records applied, verified ones only) and as the card tools see it (every record applied), and
writes each card's tree hash and each set's verified pool. ``compare`` lists the trees that
changed and the verified cards that left the pool, and names the verified cards whose play the
fixes can change with their bytes unchanged:
- fault 1: a permanent whose own static, keyword or replacement abilities read its controller
  (a ControllerRef other than ANY/OWNER, a count or history of "you", the "controller" referent,
  or a permission keyed on its controller) plays differently once its control changes; the
  verified GAIN_CONTROL carriers are what changes it in a game of these pools;
- fault 2: a SHUFFLE of an OWNER zone;
- fault 3: an activated ability that works off the battlefield.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def dump(root: Path, out: Path) -> None:
    sys.path.insert(0, str(root))
    sys.path.insert(1, str(root / "tools" / "cards"))
    import corpus

    from MTG_bot.core.ability_tree import (
        ActivatedAbility,
        Atom,
        BackFace,
        ControllerRef,
        FAtom,
        FAtomPred,
        KeywordAbility,
        QProp,
        ReplacementAbility,
        StaticAbility,
        Verb,
        Zone,
        fingerprint,
        walk,
    )
    from MTG_bot.core.executor import legality
    from MTG_bot.core.executor.games import compile_supply

    zone_of_ability = getattr(legality, "activation_zone", None)  # absent on the base
    assert Path(sys.modules["MTG_bot"].__file__).resolve().is_relative_to(root.resolve())
    implicit = {FAtomPred.CONTROLLER_COUNT_GE, FAtomPred.NAME_PARTITION_COUNT_GE}
    keyed = {Verb.ADD_LAND_PLAY, Verb.MANA_POLICY, Verb.GRANT_ACTIVATION}

    def reads_controller(ability) -> bool:
        for node in walk(ability):
            if isinstance(node, FAtom) and node.pred in implicit:
                return True
            if isinstance(node, QProp) and node.referent == "controller":
                return True
            if isinstance(node, Atom) and node.verb in keyed:
                return True
            if isinstance(node, Atom) and any(
                v not in (ControllerRef.ANY, ControllerRef.OWNER)
                for _r, v in node.args.pairs if isinstance(v, ControllerRef)
            ):
                return True
            for field in getattr(node, "__dataclass_fields__", {}):
                value = getattr(node, field)
                if isinstance(value, ControllerRef) and value not in (ControllerRef.ANY, ControllerRef.OWNER):
                    return True
        return False

    report: dict = {}
    for code in corpus.SETS:
        games = compile_supply("all", code)
        tools = compile_supply("all", code, require_verified=False)
        verified = sorted(games.verified_ids)
        names = {oid: meta.name for oid, meta in games.metas.items()}
        entry = {
            "trees": {oid: fingerprint(res.card) for oid, res in games.pool.results.items()},
            "trees_mapped": {oid: fingerprint(res.card) for oid, res in tools.pool.results.items()},
            "verified": verified,
            "names": names,
            "fault1": [], "steal": [], "fault2": [], "fault3": [],
        }
        for oid in verified:
            card = games.pool.results[oid].card
            own = [ab for ab in (*card.keywords, *card.abilities)
                   if isinstance(ab, (StaticAbility, ReplacementAbility, KeywordAbility))]
            if any(reads_controller(ab) for ab in own):
                entry["fault1"].append(names[oid])
            nodes = list(walk(card, skip=BackFace))
            if any(isinstance(n, Atom) and n.verb is Verb.GAIN_CONTROL for n in nodes):
                entry["steal"].append(names[oid])
            if any(isinstance(n, Atom) and n.verb is Verb.SHUFFLE
                   and isinstance(n.args.get("zone"), Zone)
                   and n.args.get("zone").controller is ControllerRef.OWNER for n in nodes):
                entry["fault2"].append(names[oid])
            if zone_of_ability is not None and any(
                isinstance(ab, ActivatedAbility) and zone_of_ability(ab) != "battlefield"
                for ab in card.abilities
            ):
                entry["fault3"].append(names[oid])
        report[code] = entry
    out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")


def compare(base_path: Path, head_path: Path) -> None:
    base = json.loads(base_path.read_text())
    head = json.loads(head_path.read_text())
    summary: dict = {}
    for code in head:
        b, h = base[code], head[code]
        changed = sorted(h["names"].get(oid, oid) for oid in set(b["trees"]) | set(h["trees"])
                         if b["trees"].get(oid) != h["trees"].get(oid))
        changed_mapped = sorted(oid for oid in set(b["trees_mapped"]) | set(h["trees_mapped"])
                                if b["trees_mapped"].get(oid) != h["trees_mapped"].get(oid))
        left = sorted(h["names"].get(oid, oid) for oid in set(b["verified"]) - set(h["verified"]))
        joined = sorted(h["names"].get(oid, oid) for oid in set(h["verified"]) - set(b["verified"]))
        summary[code] = {
            "trees_changed": changed, "trees_changed_with_every_record": len(changed_mapped),
            "verified": [len(b["verified"]), len(h["verified"])],
            "verified_left": left, "verified_joined": joined,
            "fault1_reads_its_controller": h["fault1"], "steal_carriers": h["steal"],
            "fault2_shuffle_owner": h["fault2"], "fault3_off_battlefield": h["fault3"],
        }
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "dump":
        dump(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        compare(Path(sys.argv[2]), Path(sys.argv[3]))
