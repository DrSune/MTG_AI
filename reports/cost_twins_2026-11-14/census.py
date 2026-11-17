"""The cost twins over the 19 sets (ontology round R11, ledger F3). Run from the repo root:

    .venv/bin/python reports/cost_twins_2026-11-14/census.py > reports/cost_twins_2026-11-14/census.txt

1. Printed costs, by the oracle text: every cost item of an activated ability ("<cost>: <effect>",
   a keyword's reminder included: "Cycling {2} ({2}, Discard this card: ...)", CR 702.29a), of an
   additional cost ("As an additional cost to cast this spell, <cost>."), of an alternative cost
   ("You may <cost> rather than pay this spell's mana cost.") and of a keyword cost written with a
   dash ("Escape—<cost>", "Kicker—<cost>"). Each item is
   classified by shape: exile (the source on the battlefield, the source in a graveyard, other
   cards from a graveyard or a hand), remove counters (from the source, from another object), and
   the existing twins (sacrifice, discard, tap, put a counter), mana and life. Per card: its state
   (cardtool: verified, mapped, needs-atom, compiled, partly-compiled, refused) and how the
   sentence compiled (records applied, verified or not).
2. The compiled side (records applied): every cost part in every tree, by class and by where it
   sits (an activated ability, a spell's additional cost, a kicker, a keyword, an effect's PAY or
   CAST), beside the verb atoms the parts mirror (SACRIFICE, TAP, PUT_COUNTER, REMOVE_COUNTER, a
   MOVE_ZONE to exile, a MOVE_ZONE from a hand to a graveyard). Trees counted per set, verified
   or not.
3. The F3 fold's reach: the verified trees whose bytes would change if the cost parts became the
   verb atoms they mirror (each would leave the verified pool until re-verified).
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "tools" / "cards", REPO / "tools"):
    sys.path.insert(0, str(p))
import MTG_bot

assert MTG_bot.__file__.startswith(str(REPO)), MTG_bot.__file__

import corpus
from cardtool import _state

from MTG_bot.core import ability_tree as at
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.executor.selectors import _filter_is_self_referential, _filter_names_the_source

_NUM = r"(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|X|\d+)"
_SELF = r"(?:this (?:artifact|creature|enchantment|land|permanent|card|Aura|Equipment|Vehicle)|~)"

#: (shape, pattern) in order; the first full match decides. Matched on one cost item, the card's
#: name written ~.
SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (shape, re.compile(pattern, re.IGNORECASE)) for shape, pattern in (
        ("mana", r"(?:\{[0-9WUBRGCXSP/]+\})+"),
        ("tap-self {T}", r"\{T\}"),
        ("untap-self {Q}", r"\{Q\}"),
        ("exile-self (battlefield)", rf"exile {_SELF}"),
        ("exile-self (graveyard)", rf"exile {_SELF} from your graveyard"),
        ("exile-self (hand)", rf"exile {_SELF} from your hand"),
        ("exile from a graveyard", rf"exile {_NUM} .*cards? from (?:your|a|any) graveyards?"),
        ("exile from a hand", rf"exile {_NUM} .*cards? from your hand"),
        ("exile (other)", r"exile .+"),
        ("remove-counter (the source)", rf"remove (?:{_NUM}|all|any number of) .*counters? from {_SELF}"),
        ("remove-counter (another object)", r"remove .+counters? from .+"),
        ("sacrifice-self", rf"sacrifice {_SELF}"),
        ("sacrifice (other)", r"sacrifice .+"),
        ("discard-self", rf"discard {_SELF}"),
        ("discard (other)", r"discard .+"),
        ("tap (other)", rf"tap (?:{_NUM}|another|any number of) .+"),
        ("put-counter", r"put .+counters? on .+"),
        ("life", r"pay (?:\d+|X) life"),
        ("mana", r"pay (?:\{[0-9WUBRGCXSP/]+\})+"),
    )
)
#: The shapes this round is about, and the existing twins (F3's four).
NEW = ("exile-self (battlefield)", "exile-self (graveyard)", "exile-self (hand)",
       "exile from a graveyard", "exile from a hand", "exile (other)",
       "remove-counter (the source)", "remove-counter (another object)")
TWINS = ("sacrifice-self", "sacrifice (other)", "discard-self", "discard (other)", "tap-self {T}",
         "tap (other)", "put-counter")

_ACTIVATED = re.compile(r'^\(?(?P<cost>[^:"]+?):\s')
_LOYALTY = re.compile(r"^\[?[+−\-]?(?:\d+|X)\]?$")
_ADDITIONAL = re.compile(r"^As an additional cost to cast this spell, (?P<cost>.+?)\.$")
_ALTERNATIVE = re.compile(r"You may (?P<cost>.+?) rather than pay this spell's mana cost")
_KEYWORD_DASH = re.compile(r"^(?P<kw>Escape|Kicker|Ward|Flashback)—(?P<cost>.+?)(?:\.|$| \()")
_VERB = re.compile(r"^(?:\{|and |exile|remove|sacrifice|discard|tap|untap|pay|put|return|reveal|mill)",
                   re.IGNORECASE)


def split_items(cost: str) -> list[str]:
    """A cost's items: comma-separated (a comma inside a list of types joins the item before it:
    Soul Diviner's "a counter from an artifact, creature, land, or planeswalker you control"), and
    "<item> and <verb> ..." split at the verb (Hellion Crucible's "Remove two pressure counters
    from this land and sacrifice it")."""
    items: list[str] = []
    for item in (x.strip() for x in cost.split(",")):
        if not item:
            continue
        if items and not _VERB.match(item):
            items[-1] = f"{items[-1]}, {item}"
            continue
        item = re.sub(r"^and ", "", item)
        parts = re.split(r" and (?=(?:sacrifice|exile|remove|discard|pay|tap) )", item, flags=re.I)
        items.extend(p.strip() for p in parts)
    return items


def classify(item: str) -> str:
    item = re.sub(r"\bit\b$", "~", item)  # "... and sacrifice it": the source
    for shape, pattern in SHAPES:
        if pattern.fullmatch(item):
            return shape
    return "other"


def cost_texts(sentence: str, name: str) -> list[tuple[str, str]]:
    """(lane, cost text) of one sentence, the card's name written ~."""
    s = sentence.replace(name, "~")
    short = name.split(",")[0]
    if short != name and len(short) > 3:
        s = s.replace(short, "~")
    out = []
    m = _ACTIVATED.match(s)
    if m and not _LOYALTY.match(m.group("cost").strip()):
        cost = m.group("cost")
        # A keyword line's reminder holds its cost ("Cycling {2} ({2}, Discard this card: Draw a
        # card.)", CR 702.29a; "Equip {1} ({1}: Attach ...)"; "Crew 2 (Tap any number of ...)").
        lane = "activated"
        if " (" in cost:
            lane = f"keyword {cost.split(' ', 1)[0]}"
            cost = cost.rsplit("(", 1)[1]
        elif "—" in cost:  # "Boast — {1}{W}"
            lane = f"keyword {cost.split(' ', 1)[0]}"
            cost = cost.split("—", 1)[1].strip()
        out.append((lane, cost))
    m = _ADDITIONAL.match(s)
    if m:
        out.append(("additional", m.group("cost")))
    m = _ALTERNATIVE.search(s)
    if m:
        out.append(("alternative", m.group("cost")))
    m = _KEYWORD_DASH.match(s)
    if m:
        out.append((f"keyword {m.group('kw')}", m.group("cost")))
    return out


# ---- the compiled side ----

PART_NAMES = {
    at.CostTap: "CostTap", at.CostSacrifice: "CostSacrifice", at.CostDiscard: "CostDiscard",
    at.CostPutCounter: "CostPutCounter", at.CostLife: "CostLife", at.CostLoyalty: "CostLoyalty",
}
for _extra in ("CostExile", "CostRemoveCounter"):  # this round's parts, where the checkout has them
    if hasattr(at, _extra):
        PART_NAMES[getattr(at, _extra)] = _extra


def part_shape(part) -> str | None:
    name = PART_NAMES.get(type(part))
    if name is None:
        return None  # mana
    if name == "CostTap":
        return "CostTap({T}: the source)" if part.target is None else "CostTap(another)"
    if name in ("CostSacrifice", "CostExile", "CostRemoveCounter", "CostPutCounter"):
        return f"{name}(the source)" if _filter_names_the_source(part.target.filter) else f"{name}(another)"
    if name == "CostDiscard":
        return f"{name}(the source)" if _filter_is_self_referential(part.target.filter) else f"{name}(another)"
    return name


def cost_lanes(card) -> list[tuple[str, at.Cost]]:
    """Every Cost of a tree but the printed mana cost, with where it sits."""
    out = []
    for node in at.walk(card):
        if isinstance(node, at.ActivatedAbility):
            out.append(("activated", node.cost))
        elif isinstance(node, at.SpellAbility):
            out.extend(("additional", c) for c in node.additional_costs)
        elif isinstance(node, at.KickerAbility):
            out.append(("kicker", node.cost))
        elif isinstance(node, at.KeywordAbility):
            out.extend((f"keyword {node.keyword.name}", c) for c in node.params if isinstance(c, at.Cost))
        elif isinstance(node, at.Atom) and node.verb in (at.Verb.PAY, at.Verb.CAST):
            cost = node.args.get("cost")
            if isinstance(cost, at.Cost):
                out.append((f"effect {node.verb.name}", cost))
    return out


def verb_shapes(card) -> set[str]:
    """The verb atoms the cost parts mirror, in a tree's effects."""
    out = set()
    for node in at.walk(card):
        if not isinstance(node, at.Atom):
            continue
        if node.verb in (at.Verb.SACRIFICE, at.Verb.TAP, at.Verb.PUT_COUNTER, at.Verb.REMOVE_COUNTER,
                         at.Verb.DISCARD, at.Verb.EXILE):
            out.add(f"verb {node.verb.name}")
        elif node.verb is at.Verb.MOVE_ZONE:
            dest, src = node.args.get("destination"), node.args.get("from")
            if isinstance(dest, at.Zone) and dest.kind is at.ZoneKind.EXILE:
                out.add("verb MOVE_ZONE -> exile")
            if (isinstance(dest, at.Zone) and dest.kind is at.ZoneKind.GRAVEYARD
                    and isinstance(src, at.Zone) and src.kind is at.ZoneKind.HAND):
                out.add("verb MOVE_ZONE hand -> graveyard (discard)")
    return out


FOLD_PARTS = ("CostSacrifice", "CostDiscard", "CostTap", "CostPutCounter")

registry = build_full_registry()
printed = []  # (set, card, state, lane, shape, item, sentence status)
compiled_parts: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
compiled_verbs: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
lanes: Counter = Counter()
fold = defaultdict(lambda: {"all": [0, 0], "no_T": [0, 0]})  # set -> {variant: [trees, verified]}
fold_cards = []
for code in corpus.SETS:
    sc = corpus.compile_set(code)
    for oid, raw in sc.raw.items():
        if raw.is_token or raw.is_emblem:
            continue
        state = _state(sc, oid)
        res = sc.results.get(oid)
        name = raw.identity.name
        sentences = (*raw.sentences, *(raw.back_face.sentences if raw.back_face else ()))
        for s in sentences:
            for lane, text in cost_texts(s, name):
                status = corpus.sentence_status(raw, res, s, registry) if res else "card refused"
                for item in split_items(text):
                    printed.append((code, name, state, lane, classify(item), item, status))
        if res is None:
            continue
        verified = state == "verified"
        shapes = set()
        names = set()
        for where, cost in cost_lanes(res.card):
            for part in cost.parts:
                shape = part_shape(part)
                if shape is None:
                    continue
                shapes.add(shape)
                lanes[(where, shape)] += 1
                names.add(PART_NAMES[type(part)])
                if PART_NAMES[type(part)] == "CostTap" and part.target is not None:
                    names.add("CostTap(another)")
        for shape in shapes:
            compiled_parts[shape][code][0] += 1
            compiled_parts[shape][code][1] += verified
        for shape in verb_shapes(res.card):
            compiled_verbs[shape][code][0] += 1
            compiled_verbs[shape][code][1] += verified
        if names & set(FOLD_PARTS):
            fold[code]["all"][0] += 1
            fold[code]["all"][1] += verified
            no_t = names & {"CostSacrifice", "CostDiscard", "CostPutCounter", "CostTap(another)"}
            if no_t:
                fold[code]["no_T"][0] += 1
                fold[code]["no_T"][1] += verified
            if verified:
                fold_cards.append((code, name, sorted(names & {*FOLD_PARTS, "CostTap(another)"})))
    print(code, "done", file=sys.stderr)


def table(rows: dict[str, dict[str, list[int]]], title: str) -> None:
    print(f"## {title}")
    print("shape | " + " | ".join(corpus.SETS) + " | total (verified)")
    for shape in sorted(rows):
        per = rows[shape]
        cells = [f"{per[c][0]}({per[c][1]})" if per[c][0] else "." for c in corpus.SETS]
        tot = sum(v[0] for v in per.values())
        ver = sum(v[1] for v in per.values())
        print(f"{shape} | " + " | ".join(cells) + f" | {tot} ({ver})")
    print()


print("# Cost twins census, the 19 sets (ontology round R11, F3)")
print("cells: trees or items n(verified); '.' none")
print()
by_shape: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
for code, name, state, lane, shape, item, status in printed:
    by_shape[shape][code][0] += 1
    by_shape[shape][code][1] += state == "verified"
table(by_shape, "1. Printed cost items, by shape (every lane)")

print("## 1a. Printed costs that exile or remove counters: every item")
print("set | card | state | lane | shape | item | how the sentence compiles")
for row in sorted(printed, key=lambda r: (NEW.index(r[4]) if r[4] in NEW else 99, r[0], r[1])):
    if row[4] in NEW:
        print(" | ".join(row))
new_rows = [r for r in printed if r[4] in NEW]
print()
print(f"{len(new_rows)} items on {len({(r[0], r[1]) for r in new_rows})} printings "
      f"({len({r[1] for r in new_rows})} names); by lane: "
      + ", ".join(f"{k} {v}" for k, v in Counter(r[3] for r in new_rows).most_common()))
print("by shape: " + ", ".join(f"{k} {v}" for k, v in Counter(r[4] for r in new_rows).most_common()))
print("by state: " + ", ".join(f"{k} {v}" for k, v in Counter(r[2] for r in new_rows).most_common()))
print()
print("## 1b. Printed cost items no shape above reads (every lane)")
for row in sorted(printed):
    if row[4] == "other":
        print(" | ".join(row))
print()
table(compiled_parts, "2. Compiled trees (records applied) holding each cost part")
table(compiled_verbs, "2a. Compiled trees holding each verb atom the parts mirror")
print("## 2b. Where the compiled cost parts sit (parts, all sets)")
for (where, shape), n in sorted(lanes.items()):
    print(f"{where} | {shape} | {n}")
print()
print("## 3. The F3 fold's reach: trees whose bytes change if CostSacrifice, CostDiscard, CostTap and")
print("##    CostPutCounter became the verb atoms they mirror (verified trees re-bake and leave the pool)")
print("set | trees (verified), every {T} included | trees (verified), the {T} symbol kept as a part")
for code in corpus.SETS:
    a, b = fold[code]["all"], fold[code]["no_T"]
    print(f"{code} | {a[0]} ({a[1]}) | {b[0]} ({b[1]})")
print(f"total | {sum(v['all'][0] for v in fold.values())} ({sum(v['all'][1] for v in fold.values())}) | "
      f"{sum(v['no_T'][0] for v in fold.values())} ({sum(v['no_T'][1] for v in fold.values())})")
print()
print("## 3a. The verified trees the fold re-bakes, with the twin parts each holds")
for code, name, names in sorted(fold_cards):
    print(f"{code} | {name} | {', '.join(names)}")
