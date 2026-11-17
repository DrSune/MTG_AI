"""Measure 2: duplicated meaning. Two parts.

    .venv/bin/python reports/component_review_2026-11-17/duplicates.py > reports/component_review_2026-11-17/duplicates.txt

A. The ledger's open classes (ATOM_DIVERGENCES, BACKLOG B-42/B-44/B-48, ontology F9/F13), each
   counted by a detector over every tree of the 19 sets with records applied: the trees on each
   side, and the verified stamps (home, reprint) whose tree holds the form a fold would rewrite.
B. By script: sentences one slot word apart (numbers, colours, card types, the card's own name or
   "this <type>") whose compiled encodings differ in more than the slot value. Every sentence the
   compiler parses on any card of the 19 sets, its template's outcome tokenised as the network
   does, slot values abstracted.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (HERE, REPO, REPO / "tools" / "cards"):
    sys.path.insert(0, str(p))
import common as C
import corpus

from MTG_bot.core.ability_tree import to_dict
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from tools.selfplay import features as FT


# ------------------------------------------------------------------ tree walking (to_dict form)

def nodes(x, path=()):
    """Every dict node of a to_dict tree, with its path of keys/roles."""
    if isinstance(x, dict):
        yield x, path
        for k, v in x.items():
            if k == "pairs":
                for role, item in v:
                    yield from nodes(item, path + (f"role:{role}",))
            else:
                yield from nodes(v, path + (k,))
    elif isinstance(x, list):
        for item in x:
            yield from nodes(item, path)


def enum(d, key):
    v = d.get(key)
    return v.get("name") if isinstance(v, dict) else v


def roles(atom):
    return dict((r, v) for r, v in atom["args"]["pairs"]) if atom.get("args") else {}


def is_atom(n, verb=None):
    return n.get("tag") == "Atom" and (verb is None or enum(n, "verb") == verb)


def fatoms(f):
    """The FAtom leaves of a filter."""
    if not isinstance(f, dict):
        return []
    if f.get("tag") == "FAtom":
        return [f]
    out = []
    for c in f.get("children") or []:
        out += fatoms(c)
    if f.get("inner"):
        out += fatoms(f["inner"])
    return out


def preds(f):
    return {enum(a, "pred") for a in fatoms(f)}


COST_PARTS = ("CostSacrifice", "CostDiscard", "CostExile", "CostTap", "CostPutCounter", "CostRemoveCounter")


def detectors():
    """name -> (description, function(tree, row) -> set of side labels the tree holds)."""
    D = {}

    def d12(t, r):
        out = set()
        for n, _ in nodes(t):
            if is_atom(n, "SEARCH"):
                out.add("controller written" if "controller" in roles(n) else "controller left out")
        return out
    D["D12 SEARCH.controller written or left out"] = d12

    def d13(t, r):
        out = set()
        for n, _ in nodes(t):
            if n.get("tag") in COST_PARTS and isinstance(n.get("target"), dict):
                out.add(f"cost victim mode {enum(n['target'], 'mode')}")
        return out
    D["D13 a cost victim's selector mode (TARGET or CHOOSE)"] = d13

    def d14(t, r):
        out = set()
        for n, _ in nodes(t):
            if n.get("tag") == "FAtom" and n.get("string_value") == "Planeswalker":
                out.add(f"{enum(n, 'pred')} Planeswalker")
        return out
    D["D14 Planeswalker as SUPERTYPE_EQ or TYPE_EQ"] = d14

    def d18(t, r):
        text = " ".join(r["sentences"] + r["back_sentences"]).lower()
        printed = "target player" in text or "target opponent" in text
        out = set()
        for n, _ in nodes(t):
            if n.get("tag") == "ControllerRef" and n.get("name") == "TARGET_PLAYER":
                out.add("TARGET_PLAYER, text prints a target player" if printed else
                        "TARGET_PLAYER, text prints none (the D18 form)")
        return out
    D["D18 'its controller' as TARGET_PLAYER"] = d18

    def d19(t, r):
        out = set()
        for n, _ in nodes(t):
            if is_atom(n, "MOVE_ZONE"):
                dest = roles(n).get("destination")
                if isinstance(dest, dict) and enum(dest, "kind") == "LIBRARY":
                    out.add("library, no position" if not dest.get("position") else f"library {enum(dest, 'position')}")
        return out
    D["D19 a move into a library with or without a position"] = d19

    def d21(t, r):
        out = set()
        for n, _ in nodes(t):
            if n.get("tag") == "EachPlayer" and isinstance(n.get("effect"), dict) and is_atom(n["effect"]):
                out.add(f"EachPlayer({enum(n, 'ref') if isinstance(n.get('ref'), dict) and n['ref'].get('tag') == 'ControllerRef' else 'ref'}) around one {enum(n['effect'], 'verb')}")
            if is_atom(n) and enum(n, "verb") in ("LOSE_LIFE", "MOVE_ZONE", "GET_EMBLEM", "GAIN_LIFE"):
                c = roles(n).get("controller")
                if isinstance(c, dict) and c.get("tag") == "ControllerRef" and c.get("name") in ("ALL_OPPONENTS", "ANY", "OPPONENT"):
                    out.add(f"plural controller on {enum(n, 'verb')}")
        return out
    D["D21 'each opponent <verb>s': EachPlayer around one atom or a plural controller"] = d21

    def d22(t, r):
        out = set()
        for ab in t["abilities"]:
            if ab.get("tag") != "StaticAbility":
                continue
            if ab.get("condition"):
                out.add("static condition")
            for n, _ in nodes(ab.get("effect")):
                if is_atom(n) and isinstance(roles(n).get("duration"), dict) and roles(n)["duration"].get("tag") == "DurationWhileCondition":
                    out.add("DurationWhileCondition on the atom")
        return out
    D["D22 'as long as' on a static: its condition or a DurationWhileCondition"] = d22

    def d23(t, r):
        out = set()
        for ab in t["abilities"]:
            if ab.get("tag") != "StaticAbility":
                continue
            kws = []
            for n, _ in nodes(ab.get("effect")):
                if is_atom(n, "GRANT_ABILITY"):
                    a = roles(n).get("ability")
                    if isinstance(a, dict) and a.get("tag") == "KeywordAbility":
                        kws.append(enum(a, "keyword"))
            if len(kws) >= 2:
                out.add("two or more grants, sorted" if kws == sorted(kws) else "two or more grants, printed order")
        return out
    D["D23 one static's keyword grants: sorted or printed order"] = d23

    def d24(t, r):
        out = set()
        for n, _ in nodes(t):
            if n.get("tag") == "ZoneChangeEvent":
                fz, tz = n.get("from_zone") or {}, n.get("to_zone") or {}
                if enum(fz, "kind") == "BATTLEFIELD" and enum(tz, "kind") == "GRAVEYARD":
                    subj = n.get("subject")
                    creature = any(a.get("string_value") == "Creature" for a in fatoms(subj))
                    out.add("zone change BF->GY, creature subject" if creature else "zone change BF->GY, other subject")
            if n.get("tag") == "CreatureDiesEvent":
                out.add("CreatureDiesEvent")
        return out
    D["D24 'dies' as CreatureDiesEvent or a zone change"] = d24

    def d25(t, r):
        out = set()
        for n, _ in nodes(t):
            if n.get("tag") in COST_PARTS and isinstance(n.get("target"), dict):
                f = n["target"].get("filter") or {}
                ps = preds(f)
                if f.get("tag") == "FAtom" and enum(f, "pred") == "IS_SOURCE":
                    out.add(f"{n['tag']}: IS_SOURCE alone")
                elif f.get("tag") == "FAnd" and ps == {"IS_SOURCE", "CONTROLLER_IS"}:
                    out.add(f"{n['tag']}: FAnd(CONTROLLER_IS YOU, IS_SOURCE)")
        return out
    D["D25 'this <permanent>' as a cost's object"] = d25

    def b42(t, r):
        out = set()
        for n, _ in nodes(t):
            if is_atom(n, "MOVE_ZONE"):
                rs = roles(n)
                out.add("moved objects in role:cards" if "cards" in rs else
                        ("moved objects in role:target" if "target" in rs else "neither"))
                dest = rs.get("destination")
                if isinstance(dest, dict) and enum(dest, "kind") == "HAND":
                    who = enum(dest, "controller")
                    if who in ("OWNER", "ANY"):
                        out.add(f"to Zone(HAND, {who})")
        return out
    D["B-42 MOVE_ZONE: the moved objects' role; 'its owner's hand'"] = b42

    def b48(t, r):
        out = set()
        for n, _ in nodes(t):
            if is_atom(n, "DISCARD"):
                out.add("Verb.DISCARD")
            if is_atom(n, "MOVE_ZONE"):
                rs = roles(n)
                src = rs.get("cards") or rs.get("target")
                zs = (src or {}).get("zones") or [] if isinstance(src, dict) else []
                dest = rs.get("destination") or {}
                if any(enum(z, "kind") == "HAND" for z in zs) and enum(dest, "kind") == "GRAVEYARD":
                    out.add("MOVE_ZONE hand->graveyard")
        return out
    D["B-48 discard: Verb.DISCARD or MOVE_ZONE from a hand to a graveyard"] = b48

    legacy = ("DIED_THIS_TURN", "LIFE_GAINED_THIS_TURN_GE", "CARDS_DRAWN_THIS_TURN_GE", "MOVED_TO_ZONE_THIS_TURN",
              "INSTANT_OR_SORCERY_CAST_THIS_TURN", "CAST_THIS_TURN_FROM", "ENTERED_THIS_TURN_FROM",
              "NOT_FIRST_DRAW_THIS_STEP", "ATTACK_AGAINST_COUNT_GE", "WAS_CAST_THIS_TURN")

    def b44(t, r):
        out = set()
        for n, _ in nodes(t):
            if n.get("tag") == "FAtom":
                p = enum(n, "pred")
                if p in legacy:
                    out.add(f"legacy {p}")
                elif p in ("EVENT_THIS_TURN", "SUBJECT_OF_EVENT_THIS_TURN"):
                    out.add(f"general {p}")
            if n.get("tag") == "QThisTurn":
                out.add("legacy QThisTurn")
        return out
    D["B-44 turn history: the legacy predicates or EVENT_THIS_TURN"] = b44

    cmp_ = ("POWER_LE", "POWER_GE", "CMC_LE", "CMC_GE", "PT_LE", "PT_GE", "COLOR_COUNT_GE", "LIFE_TOTAL_GE",
            "LIFE_LEAD_OVER_START_GE", "CONTROLLER_COUNT_GE", "CONTROLLER_COUNT_LE", "CONTROLLER_COUNT_GT",
            "ZONE_COUNT_GE", "NAME_PARTITION_COUNT_GE")

    def comparators(t, r):
        out = set()
        for n, path in nodes(t):
            if n.get("tag") == "FNot" and isinstance(n.get("inner"), dict) and n["inner"].get("tag") == "FAtom":
                p = enum(n["inner"], "pred")
                if p in cmp_:
                    out.add(f"FNot({p})")
            if n.get("tag") == "FAtom" and enum(n, "pred") in cmp_:
                out.add(enum(n, "pred"))
        return out
    D["Comparators: the threshold predicates, LE forms and FNot(GE) forms"] = comparators

    def policies(t, r):
        return {f"Verb.{enum(n, 'verb')}" for n, _ in nodes(t) if is_atom(n) and enum(n, "verb") in
                ("MANA_POLICY", "DAMAGE_ASSIGN_POLICY", "ATTACK_POLICY", "MANDATE_ATTACK", "MANDATE_BLOCK")}
    D["F9 the 'as though' policies and the requirements"] = policies

    def f13(t, r):
        out = set()
        for n, _ in nodes(t):
            if n.get("tag") == "Choose":
                opts = n.get("options") or []
                colors = set()
                for o in opts:
                    toks = FT.ir_tokens(o)
                    colors |= {x for x in toks if x in ("str:W", "str:U", "str:B", "str:R", "str:G")}
                if len(opts) == 5 and len(colors) == 5:
                    out.add("Choose over five colours (resolution)")
            if is_atom(n, "CHOOSE_NAME") and "quality" in roles(n):
                out.add(f"CHOOSE_NAME quality {roles(n)['quality']}")
        return out
    D["F13 'choose a colour': a Choose over five or CHOOSE_NAME(COLOR)"] = f13

    def d2(t, r):
        out = set()
        for n, _ in nodes(t):
            if n.get("tag") == "Selector" and enum(n, "mode") == "ALL":
                c = n.get("count") or {}
                out.add(f"ALL count {c.get('tag')}" + (f"({c.get('n', c.get('value'))})" if c.get("tag") in ("QAtLeast", "QConst") else ""))
        return out
    D["D2 / B-backlog 'ALL's count': what an ALL selector's count holds"] = d2

    def d1d4(t, r):
        out = set()
        for n, _ in nodes(t):
            if n.get("tag") == "FNot" and isinstance(n.get("inner"), dict) and n["inner"].get("tag") in ("FAnd", "FOr"):
                out.add(f"FNot({n['inner']['tag']})")
            if n.get("tag") == "FOr":
                kids = n.get("children") or []
                ands = [k for k in kids if k.get("tag") == "FAnd"]
                if len(ands) >= 2:
                    common = None
                    for k in ands:
                        s = {json.dumps(c, sort_keys=True) for c in k.get("children") or []}
                        common = s if common is None else common & s
                    if common:
                        out.add("FOr of FAnds sharing a conjunct (un-distributed)")
        return out
    D["D1/D4 negation placement and un-distributed FOr"] = d1d4

    def enumerations(t, r):
        out = set()
        for n, _ in nodes(t):
            if n.get("tag") == "Choose":
                opts = [FT.ir_tokens(o) for o in n.get("options") or []]
                if len(opts) >= 2:
                    base = Counter(opts[0])
                    near = all(sum((Counter(o) - base).values()) + sum((base - Counter(o)).values()) <= 0.3 * len(o)
                               for o in opts[1:])
                    if near:
                        out.add(f"Choose over {len(opts)} near-identical options")
        return out
    D["Enumerations: a Choose whose options repeat one subtree (and/or, colour of your choice)"] = enumerations

    def source_object(t, r):
        """'this <permanent>' as an effect's object (not a cost's, D25): which selector form."""
        out = set()
        for n, path in nodes(t):
            if n.get("tag") != "Selector" or any(p in ("parts",) for p in path):
                continue
            f = n.get("filter") or {}
            ps = preds(f)
            bare = f.get("tag") == "FAtom" and enum(f, "pred") == "IS_SOURCE"
            yours = f.get("tag") == "FAnd" and ps == {"IS_SOURCE", "CONTROLLER_IS"}
            if bare or yours:
                c = n.get("count") or {}
                cnt = c.get("tag") + (f"({c.get('value')})" if c.get("tag") == "QConst" else "")
                zs = ",".join(sorted(f"{enum(z, 'kind')}/{enum(z, 'controller')}" for z in n.get("zones") or []))
                out.add(f"{enum(n, 'mode')} {cnt} {'IS_SOURCE' if bare else 'FAnd(CONTROLLER_IS YOU, IS_SOURCE)'} [{zs}]")
            if n.get("referent") == "source":
                out.add("Selector(referent='source')")
        return out
    D["The source as an effect's object: which selector form"] = source_object

    def selfname(t, r):
        out = set()
        for n, _ in nodes(t):
            if n.get("tag") == "FAtom" and enum(n, "pred") == "NAME_EQ":
                out.add("NAME_EQ its own name" if n.get("string_value") == r["name"] else "NAME_EQ another card's name")
            if n.get("tag") == "FAtom" and enum(n, "pred") == "NAME_CONTAINS":
                out.add("NAME_CONTAINS (a planeswalker's name)")
        return out
    D["Names: NAME_EQ of the card itself or of another card"] = selfname
    return D


def part_a(rows: list[dict]) -> None:
    print("# A. The ledger's classes, by detector (trees of the 19 sets with records applied)")
    print("columns: trees (distinct oracle ids) | verified home stamps (M21, M20, FDN) | verified reprint stamps")
    D = detectors()
    trees = [r for r in rows if "tree" in r]
    for name, fn in D.items():
        side_oids = defaultdict(set)
        side_home = defaultdict(list)
        side_rep = defaultdict(int)
        for r in trees:
            for side in fn(r["tree"], r):
                side_oids[side].add(r["oid"])
                if r["state"] == "verified":
                    if r["reprint_of"]:
                        side_rep[side] += 1
                    else:
                        side_home[side].append(f"{r['set']} {r['name']}")
        print(f"\n## {name}")
        if not side_oids:
            print("  (no tree)")
        for side in sorted(side_oids, key=lambda s: -len(side_oids[s])):
            homes = side_home[side]
            ex = "; ".join(sorted(homes)[:10]) + (" ..." if len(homes) > 10 else "")
            print(f"  {side:58s} {len(side_oids[side]):5d} | {len(homes):4d} | {side_rep[side]:4d}   {ex}")


# ------------------------------------------------------------------ part B

_SELF = re.compile(r"\bthis (?:creature|artifact|enchantment|land|permanent|Equipment|Aura|Vehicle|card|spell|planeswalker)\b")
_TYPE_STR = {"Creature", "Artifact", "Enchantment", "Land", "Planeswalker", "Instant", "Sorcery", "Player",
             "Legendary", "Basic"}
_COLOR_STR = {"W", "U", "B", "R", "G"}


def shape(sentence: str, name: str) -> str:
    s = C.norm_sentence(sentence, name)
    s = _SELF.sub("~", s)
    return C.slot_shape(s)


def abstract(tokens: list[str]) -> tuple:
    out = []
    for t in tokens:
        if t.startswith("num:") or t in ("QX",):
            out.append("NUM")
        elif t.startswith("str:") and t[4:] in _TYPE_STR:
            out.append("TYPE")
        elif t.startswith("str:") and t[4:] in _COLOR_STR:
            out.append("COLOR")
        elif t.startswith("PtDirection."):
            out.append("DIR")
        else:
            out.append(t)
    return tuple(out)


def part_b(rows: list[dict]) -> None:
    registry = build_full_registry()
    groups = defaultdict(lambda: defaultdict(list))
    n_sent = 0
    seen = set()
    for code in corpus.SETS:
        raw = ingest_pool(REPO / "MTG_bot" / "data" / f"{code}.json")
        for oid, rc in raw.items():
            if rc.is_token or rc.is_emblem:
                continue
            for s in rc.sentences:
                key = (oid, s)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    ms = registry.match(s)
                except Exception:  # noqa: BLE001 - a template's build may refuse out of context
                    continue
                if not ms:
                    continue
                tree = corpus._outcome_tree(ms[0].outcome)
                try:
                    d = to_dict(tree)
                except Exception:  # noqa: BLE001
                    continue
                toks = FT.ir_tokens(d)
                if not toks:
                    continue
                n_sent += 1
                groups[shape(s, rc.identity.name)][abstract(toks)].append(
                    (code, rc.identity.name, s, ms[0].template.tid))
    print(f"\n\n# B. Sentences one slot word apart with different encodings")
    print(f"{n_sent} parsed (card, sentence) pairs of the 19 sets; {len(groups)} slot shapes; "
          "a shape with two or more abstracted encodings is listed (slot values: numbers, colours, "
          "card types; the card's name and 'this <type>' as ~)")
    multi = {k: v for k, v in groups.items() if len(v) >= 2}
    print(f"shapes with two or more encodings: {len(multi)} "
          f"(sentences in them: {sum(len(x) for v in multi.values() for x in v.values())})")
    for k, v in sorted(multi.items(), key=lambda kv: -sum(len(x) for x in kv[1].values())):
        print(f"\n[{sum(len(x) for x in v.values())}] {k}")
        encs = sorted(v.items(), key=lambda kv: -len(kv[1]))
        base = Counter(encs[0][0])
        for enc, items in encs:
            diff_plus = sorted((Counter(enc) - base).elements())
            diff_minus = sorted((base - Counter(enc)).elements())
            ex = items[0]
            tids = sorted({i[3] for i in items})
            print(f"   {len(items):3d} x  e.g. {ex[0]} {ex[1]}: \"{ex[2][:90]}\"  [{', '.join(tids)[:80]}]")
            if diff_plus or diff_minus:
                print(f"         vs the first: +{diff_plus[:12]} -{diff_minus[:12]}")


def part_c(rows: list[dict]) -> None:
    """Whole cards: every compiled card of the 19 sets (records applied) keyed by its printed text
    with slots freed; a key whose cards carry two or more abstracted trees is listed."""
    groups = defaultdict(lambda: defaultdict(list))
    seen = set()
    for r in rows:
        if "tokens" not in r or r["oid"] in seen or not r["sentences"]:
            continue
        if r["unparsed"] or r["back_unparsed"]:
            continue  # a partly compiled card's tree is not its text's meaning
        seen.add(r["oid"])
        key = tuple(shape(s, r["name"]) for s in r["sentences"])
        toks = [t for t in r["tokens"][len(r["face"]):]]
        toks = [("str:~" if t == f"str:{r['name']}" else t) for t in toks]
        groups[key][abstract(toks)].append(r)
    multi = {k: v for k, v in groups.items() if len(v) >= 2}
    print("\n\n# C. Whole cards with the same text up to slot words (wholly compiled, records applied)")
    print(f"{len(groups)} texts; texts whose cards carry two or more encodings beyond the slot values: {len(multi)}")
    for k, v in sorted(multi.items(), key=lambda kv: -sum(len(x) for x in kv[1].values())):
        print(f"\n[{sum(len(x) for x in v.values())}] " + " / ".join(k)[:200])
        encs = sorted(v.items(), key=lambda kv: -len(kv[1]))
        base = Counter(encs[0][0])
        for enc, items in encs:
            plus = sorted((Counter(enc) - base).elements())
            minus = sorted((base - Counter(enc)).elements())
            states = Counter(("record" if i["record"] else "compiler") + "/" + i["state"] for i in items)
            names = ", ".join(f"{i['set']} {i['name']}" for i in items[:5])
            print(f"   {len(items):3d} x {dict(states)}  e.g. {names}")
            if plus or minus:
                print(f"         vs the first: +{plus[:14]} -{minus[:14]}")


def main() -> None:
    rows = C.load()
    part_a(rows)
    part_b(rows)
    part_c(rows)


if __name__ == "__main__":
    main()
