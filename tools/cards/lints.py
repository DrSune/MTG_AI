"""Static checks of a card's tree against its printed text, for the defect classes the onboarding
waves found most often (KNOWLEDGE/2026-11-14/207). They run inside gate G0, so a mapper sees them at
``cardtool try`` and ``write``, and ``cardtool verify`` refuses a card that fails one.

- ``players``: who acts or whose objects (29 of 75 planted faults; FDN Pilfer's first record wrote
  "target opponent" as any player, M21 Necromentia gave the caster the Zombies). An opponent-side
  player in the tree needs opponent wording in the text, and the reverse; a designated player
  needs its own words ("target player", "target opponent"); "<subject> <verb>s" needs an atom of
  that verb acting for that side, and one at all (M21 Peer into the Abyss lost its life loss).
- ``costs``: every printed activated ability's cost ("{3}{U}, {T}, Sacrifice this creature:",
  "Equip {3}", "[+1]:") equals a top-level activated ability's cost, part for part, and the tree has
  no activation the text does not print (6 of 75 plants; M21 Azusa's land plays as a free
  activation, which the network used nine times a turn).
- ``amounts``: no number of two or more in the tree that the text never prints (an amount one
  too high is the commonest plant, 25 of 75).
- ``carrier``: a permanent card's cast carrier holds no effect: an effect there happens when the
  card is CAST (the orphaned "If you do, draw a card." of 23 partly compiled cards, M20 Keldon
  Raider; M20 Sorin, Vampire Lord gaining 4 life as it was cast).

Each check returns plain-language findings; an empty list is a pass. ``EXCEPTIONS`` lists the
justified exceptions by oracle id, each with its reason. Over every verified card of M21, M20 and
FDN they find nothing but the one listed exception (``test_lints.py``).
"""

from __future__ import annotations

import dataclasses
import re
from collections import Counter
from collections.abc import Iterator
from typing import Any

from MTG_bot.core.ability_tree import (
    QX,
    ActivatedAbility,
    Atom,
    AtomArgs,
    BackFace,
    CardRecord,
    ControllerRef,
    CostLife,
    CostLoyalty,
    CostManaColor,
    CostManaGeneric,
    CostManaHybrid,
    CostSacrifice,
    CostTap,
    EachPlayer,
    FAtom,
    FAtomPred,
    QConst,
    Selector,
    SpellAbility,
    Verb,
    walk,
)
from MTG_bot.core.compiler.ingest import RawCard

#: (lint, oracle id) -> why the finding is right to ignore. Add one only with the reason, and say
#: so in the card's review; a lint that needs many is a wrong lint.
EXCEPTIONS: dict[tuple[str, str], str] = {
    ("players", "93cf50cf-0ecc-4d3e-abea-778c1ebacec4"): (
        "Massacre Wurm (M21, FDN): \"that creature's controller loses 2 life\" is the last "
        "TARGET_PLAYER antecedent, divergence D18 (docs/ATOM_DIVERGENCES.md); its fold to "
        "Selector(referent='event') is scheduled (BACKLOG B-114), and "
        "tools/audit/test_ontology_conformance.py flags the same card"),
}

OPPONENT_SIDE = frozenset({ControllerRef.OPPONENT, ControllerRef.ALL_OPPONENTS,
                           ControllerRef.TARGET_OPPONENT, ControllerRef.DEFENDING_PLAYER})
_OPPONENT_WORDS = re.compile(r"\bopponents?\b|\bopponent's\b|\bdon't control\b|\bdoesn't control\b"
                             r"|\bdefending player\b", re.IGNORECASE)
_PERMANENT_TYPES = ("Creature", "Artifact", "Enchantment", "Planeswalker", "Battle")


def rules_text(raw: RawCard) -> list[str]:
    """The front face's rules sentences, reminder text left out, the card's own name as ``~``."""
    out = []
    name = raw.identity.name
    short = name.split(",")[0]
    for sentence in raw.sentences:
        s = re.sub(r"\s*\([^)]*\)", "", sentence).strip()
        s = s.replace(name, "~")
        if short != name and len(short) > 3:
            s = s.replace(short, "~")
        if s:
            out.append(s)
    return out


def _front(card: CardRecord) -> list[Any]:
    return [a for a in card.abilities if not isinstance(a, BackFace)]


def _refs(node: Any) -> Iterator[ControllerRef]:
    """Every ControllerRef in a subtree (zones, filters, roles, EachPlayer), back faces left out."""
    if isinstance(node, ControllerRef):
        yield node
    elif isinstance(node, BackFace):
        return
    elif isinstance(node, AtomArgs):
        for _, value in node.pairs:
            yield from _refs(value)
    elif dataclasses.is_dataclass(node) and not isinstance(node, type):
        for f in dataclasses.fields(node):
            yield from _refs(getattr(node, f.name))
    elif isinstance(node, (tuple, list, frozenset)):
        for item in node:
            yield from _refs(item)


# ----------------------------------------------------------------------------- players
#: Printed verbs whose actor the tree names, and the atoms that perform them.
_VERBS = {
    "create": (Verb.CREATE_TOKEN,),
    "draw": (Verb.DRAW,),
    "discard": (Verb.DISCARD, Verb.MOVE_ZONE),
    "lose": (Verb.LOSE_LIFE,),
    "gain": (Verb.GAIN_LIFE,),
    "sacrifice": (Verb.SACRIFICE,),
    "mill": (Verb.MILL, Verb.MOVE_ZONE),
    "scry": (Verb.SCRY,),
}
_SUBJECT = re.compile(r"\b(each opponent|target opponent|that player|its controller|defending player|"
                      r"target player|each player|you)\b", re.IGNORECASE)
_VERB = re.compile(r"\b(creates?|draws?|discards?|loses?|gains?|sacrifices?|mills?|scry|scries)\b",
                   re.IGNORECASE)
#: What may stand between a subject and its verb: "you may draw", "that player shuffles, then
#: creates", "target player draws two cards and loses 2 life".
_LINK = re.compile(r"^(?:\s+(?:may|then|also|can))*\s+$|(?:,\s*then|\band(?:\s+then)?)\s+$", re.IGNORECASE)


def _stem(verb: str, rest: str) -> str | None:
    v = verb.lower()
    stem = {"creates": "create", "draws": "draw", "discards": "discard", "loses": "lose",
            "gains": "gain", "sacrifices": "sacrifice", "mills": "mill", "scries": "scry"}.get(v, v)
    if stem in ("gain", "lose") and not re.match(r"^(?:\s+\S+){0,4}?\s+life\b", rest):
        return None  # "gain control", "loses flying"
    return stem


def subject_verbs(sentence: str) -> list[tuple[str, str, str]]:
    """(subject, verb stem, the words) for each instruction "<subject> <verb>s" of a sentence,
    a trigger's event clause left out ("Whenever you gain life" is an event, not an instruction).
    A quoted ability is read as a sentence of its own."""
    quotes = re.findall(r'"([^"]*)"', sentence)
    if quotes:
        outer = re.sub(r'"[^"]*"', " an ability ", sentence)
        return [sv for part in (outer, *quotes) for sv in subject_verbs(part)]
    out = []
    head = _trigger_head(sentence)
    subjects = [m for m in _SUBJECT.finditer(sentence) if m.start() >= head]
    for i, m in enumerate(subjects):
        end = subjects[i + 1].start() if i + 1 < len(subjects) else len(sentence)
        segment = sentence[m.end():end]
        segment = re.split(r"[.;]", segment, maxsplit=1)[0]
        for v in _VERB.finditer(segment):
            if not _LINK.search(segment[:v.start()]) and segment[:v.start()].strip():
                continue
            stem = _stem(v.group(1), segment[v.end():])
            if stem is not None:
                out.append((m.group(1).lower(), stem, (m.group(0) + segment[:v.end()]).strip()))
    return out


def _player(node: Any) -> str:
    if isinstance(node, ControllerRef):
        return node.name
    if isinstance(node, Selector) and node.referent is not None:
        return f"referent:{node.referent}"
    return "OTHER"


def _conjuncts(f: Any) -> list[Any]:
    return list(f.children) if type(f).__name__ == "FAnd" else [f]


def _sacrificer(sel: Any) -> Any:
    """Who sacrifices: a permanent's controller does (CR 701.21a), so the selector's own
    CONTROLLER_IS, else its zone's controller when that names one player."""
    if not isinstance(sel, Selector):
        return None
    for c in _conjuncts(sel.filter):
        if isinstance(c, FAtom) and c.pred is FAtomPred.CONTROLLER_IS and c.who is not None:
            return c.who
    zones = sel.zones or ()
    if zones and zones[0].controller is not ControllerRef.ANY:
        return zones[0].controller
    return None


def _actors(card: CardRecord) -> list[tuple[Verb, str, Atom]]:
    """(verb, who acts, atom) for every atom of the front face; inside an EachPlayer the atom's
    own "you" is each of its players (the executor rotates the controller there)."""
    out: list[tuple[Verb, str, Atom]] = []

    def visit(node: Any, each: str | None) -> None:
        if isinstance(node, BackFace):
            return
        if isinstance(node, EachPlayer):
            each = _player(node.ref)
        if isinstance(node, Atom):
            who = node.args.get("controller")
            if who is None and node.verb is Verb.SACRIFICE:
                who = _sacrificer(node.args.get("target"))
            if who is None and node.verb is Verb.MOVE_ZONE:
                sel = node.args.get("cards")
                zones = getattr(sel, "zones", ()) or ()
                who = zones[0].controller if zones else None
            name = _player(who) if who is not None else "YOU"
            if each is not None and name == "YOU":
                name = each
            out.append((node.verb, name, node))
        if isinstance(node, AtomArgs):
            for _, value in node.pairs:
                visit(value, each)
        elif dataclasses.is_dataclass(node) and not isinstance(node, type):
            for f in dataclasses.fields(node):
                visit(getattr(node, f.name), each)
        elif isinstance(node, (tuple, list, frozenset)):
            for item in node:
                visit(item, each)

    for ability in _front(card):
        visit(ability, None)
    return out


def _is_discard(atom: Atom) -> bool:
    if atom.verb is Verb.DISCARD:
        return True
    if atom.verb is not Verb.MOVE_ZONE:
        return False
    kind = atom.args.get("journal_kind")
    return str(kind) == "DISCARD" or (getattr(atom.args.get("from"), "kind", None) is not None
                                      and atom.args.get("from").kind.name == "HAND"
                                      and getattr(atom.args.get("destination"), "kind", None) is not None
                                      and atom.args.get("destination").kind.name == "GRAVEYARD")


def _is_mill(atom: Atom) -> bool:
    return atom.verb is Verb.MILL or (atom.verb is Verb.MOVE_ZONE and str(atom.args.get("journal_kind")) == "MILL")


def _performs(stem: str, verb: Verb, atom: Atom) -> bool:
    if verb not in _VERBS[stem]:
        return False
    if stem == "discard" and verb is Verb.MOVE_ZONE:
        return _is_discard(atom)
    if stem == "mill" and verb is Verb.MOVE_ZONE:
        return _is_mill(atom)
    return True


def _trigger_head(sentence: str) -> int:
    """Where a trigger's event clause ends (its first comma), else 0: "Whenever you gain life, ..."
    names an event, not an instruction."""
    if re.match(r"^(when|whenever|at)\b", sentence, re.IGNORECASE):
        comma = sentence.find(",")
        return comma if comma > 0 else len(sentence)
    return 0


def _opponent_side(card: CardRecord) -> set[str]:
    """The opponent-side players the tree names: the refs, and "an opponent" as OPPONENT_OF you."""
    side = {r.name for r in _refs(_front(card)) if r in OPPONENT_SIDE}
    for ability in _front(card):
        for n in walk(ability, skip=BackFace):
            if isinstance(n, FAtom) and n.pred is FAtomPred.OPPONENT_OF and n.who is ControllerRef.YOU:
                side.add("OPPONENT_OF YOU")
    return side


def players(raw: RawCard, card: CardRecord) -> list[str]:
    text = " ".join(rules_text(raw))
    found: list[str] = []
    refs = set(_refs(_front(card)))
    opp = _opponent_side(card)
    # A keyword's reminder text may be where the opponent is named (Bloodthirst).
    if opp and not _OPPONENT_WORDS.search(" ".join(raw.sentences)):
        found.append("the tree names an opponent-side player (" + ", ".join(sorted(opp))
                     + ") but the text never names an opponent: check every controller and CONTROLLER_IS")
    if re.search(r"\b(each|target|an) opponents?\b|\byour opponents\b", text, re.IGNORECASE) and not opp:
        found.append("the text names an opponent but no opponent-side player is in the tree: an "
                     "opponent's action or object was given to you")
    says_target_opponent = re.search(r"\btarget opponent\b", text, re.IGNORECASE) is not None
    # "Target opponent reveals their hand. ... That player discards": TARGET_PLAYER may read the
    # binding a TARGET_OPPONENT designated (DESIGNATED_PLAYER_REFS), never designate one itself.
    if (ControllerRef.TARGET_PLAYER in refs and not re.search(r"\btarget player\b", text, re.IGNORECASE)
            and not (says_target_opponent and ControllerRef.TARGET_OPPONENT in refs)):
        found.append('the tree designates "target player" (any player, you included) but the text '
                     'never says "target player"' + (' (it says "target opponent")' if says_target_opponent else ""))
    if ControllerRef.TARGET_OPPONENT in refs and not says_target_opponent:
        found.append('the tree designates "target opponent" but the text never says "target opponent"')
    actors = _actors(card)
    for sentence in rules_text(raw):
        for subj, stem, words in subject_verbs(sentence):
            doers = {who for verb, who, atom in actors if _performs(stem, verb, atom)}
            if not doers:
                found.append(f'"{words[:70]}": the text says {subj} {stem}s, but no {stem} is in the tree '
                             "(a dropped instruction)")
            elif subj == "you" and "YOU" not in doers:
                found.append(f'"{words[:70]}": the text says you {stem}, but every {stem} in the tree is '
                             f"for {sorted(doers)}")
            elif subj not in ("you", "each player") and doers == {"YOU"}:
                found.append(f'"{words[:70]}": the text says {subj} {stem}s, but every {stem} in the tree '
                             "is for you")
    return found


# ----------------------------------------------------------------------------- costs
_MANA = re.compile(r"\{([^}]+)\}")
_TAP_OTHER = r"^tap (?:an?|one|two|three|four|five|x|\d+) untapped "


def _mana_parts(text: str) -> Counter:
    c: Counter = Counter()
    for sym in _MANA.findall(text):
        s = sym.upper()
        if s.isdigit():
            c["generic"] += int(s)
        elif s == "X":
            c["X"] += 1
        elif s in ("W", "U", "B", "R", "G", "C"):
            c[s] += 1
        elif "/" in s:
            c["hybrid:" + "/".join(sorted(s.split("/")))] += 1
        elif s in ("T",):
            c["tap"] += 1
        elif s == "Q":
            c["untap"] += 1
        else:
            c["?" + s] += 1
    return c


def printed_cost(cost: str) -> Counter | None:
    """The cost parts a printed activated ability names, or None when it names one this check does
    not read (then the ability is left to the other gates)."""
    parts: Counter = Counter()
    for piece in re.split(r",\s*", cost.strip()):
        p = piece.strip()
        low = p.lower()
        if re.fullmatch(r"(\{[^}]+\})+", p):
            parts += _mana_parts(p)
        elif re.match(r"^sacrifice (this|~)\b", low):
            parts["sacrifice:self"] += 1
        elif low.startswith("sacrifice "):
            parts["sacrifice:other"] += 1
        elif m := re.fullmatch(r"pay (\d+) life", low):
            parts[f"life:{m.group(1)}"] += 1
        elif low.startswith("discard "):
            parts["discard"] += 1
        elif re.match(_TAP_OTHER, low):
            parts["tap:other"] += 1
        else:
            return None  # exile, remove counters, return, put counters, ...: not read here
    return parts


def tree_cost(ability: ActivatedAbility) -> Counter | None:
    parts: Counter = Counter()
    for part in ability.cost.parts:
        if isinstance(part, CostManaGeneric):
            if isinstance(part.amount, QConst):
                parts["generic"] += part.amount.value
            elif isinstance(part.amount, QX):
                parts["X"] += 1
            else:
                return None
        elif isinstance(part, CostManaColor):
            if not isinstance(part.amount, QConst):
                return None
            parts[part.color] += part.amount.value
        elif isinstance(part, CostManaHybrid):
            if not isinstance(part.amount, QConst):
                return None
            parts["hybrid:" + "/".join(sorted(part.colors))] += part.amount.value
        elif isinstance(part, CostTap):
            parts["tap" if part.target is None else "tap:other"] += 1
        elif isinstance(part, CostSacrifice):
            self_ = any(isinstance(c, FAtom) and c.pred is FAtomPred.IS_SOURCE
                        for c in _conjuncts(part.target.filter))  # "another" is FNot(IS_SOURCE)
            parts["sacrifice:self" if self_ else "sacrifice:other"] += 1
        elif isinstance(part, CostLife):
            if not isinstance(part.amount, QConst):
                return None
            parts[f"life:{part.amount.value}"] += 1
        elif isinstance(part, CostLoyalty):
            parts[f"loyalty:{part.delta}" if isinstance(part.delta, int) else "loyalty:X"] += 1
        elif type(part).__name__ == "CostDiscard":
            parts["discard"] += 1
        else:
            return None
    return parts


_LOYALTY = re.compile(r"^\[([+\-−]?)(\d+|X)\]:\s")
_EQUIP = re.compile(r"^Equip (\{[^}]+\}(?:\{[^}]+\})*)$")


def printed_activations(raw: RawCard) -> list[tuple[str, Counter | None]]:
    """(the printed line, its cost parts) for each activated ability of the front face."""
    out = []
    lines = rules_text(raw)
    if "Land" in raw.type_line:
        # A basic land type's mana ability is intrinsic (CR 305.6); the card prints it as reminder
        # text, "({T}: Add {G}.)", which rules_text leaves out.
        lines += [m.group(1) for s in raw.sentences if (m := re.fullmatch(r"\((\{T\}: Add [^)]*)\)", s.strip()))]
    for s in lines:
        if s.startswith(('"', "•")):
            continue
        if m := _LOYALTY.match(s):
            sign, n = m.group(1), m.group(2)
            if n == "X":
                out.append((s, Counter({"loyalty:X": 1})))
            else:
                v = int(n) * (-1 if sign in ("-", "−") else 1)
                out.append((s, Counter({f"loyalty:{v}": 1})))
            continue
        if m := _EQUIP.match(s):
            out.append((s, _mana_parts(m.group(1))))
            continue
        head, sep, _ = s.partition(": ")
        if not sep or '"' in head or len(head) > 80:
            continue
        if not (head.startswith("{") or re.match(r"^(Sacrifice|Pay|Discard|Exile|Remove|Return|Put)\b", head)
                or re.match(_TAP_OTHER, head.lower())):
            continue
        out.append((s, printed_cost(head)))
    return out


def costs(raw: RawCard, card: CardRecord) -> list[str]:
    printed = printed_activations(raw)
    if any(p is None for _, p in printed):
        return []
    tree = [tree_cost(a) for a in _front(card) if isinstance(a, ActivatedAbility)]
    if any(t is None for t in tree):
        return []
    if not printed and not tree:
        return []
    want = Counter(tuple(sorted(p.items())) for _, p in printed)
    have = Counter(tuple(sorted(t.items())) for t in tree)
    if want == have:
        return []
    missing = want - have
    extra = have - want
    found = []
    for sig in missing:
        line = next(s for s, p in printed if tuple(sorted(p.items())) == sig)
        found.append(f"no activated ability in the tree costs what {line.split(':')[0]!r} prints "
                     f"({dict(sig)}); the tree has {[dict(t) for t in extra] or 'nothing left'}")
    if not missing and extra:
        found.append(f"activated abilities in the tree with no printed cost: {[dict(t) for t in extra]}")
    return found


# ----------------------------------------------------------------------------- amounts
_WORD_NUMBERS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                 "ten": 10, "twice": 2, "double": 2, "doubles": 2, "half": 2, "triple": 3, "thrice": 3}


def printed_numbers(raw: RawCard) -> set[int]:
    """Every number of two or more the rules text states, in digits or words ("half" and "twice"
    are 2), its P/T and loyalty included."""
    text = " ".join(rules_text(raw))
    nums = {int(n) for n in re.findall(r"(?<![\w])[+\-−]?(\d+)", text)}
    nums |= {_WORD_NUMBERS[w.lower()] for w in re.findall(r"\b(" + "|".join(_WORD_NUMBERS) + r")\b", text, re.IGNORECASE)}
    nums |= {len(m.group(0)) // 3 for m in re.finditer(r"(\{[WUBRGC]\})\1+", text)}  # "Add {G}{G}"
    for v in (raw.power_raw, raw.toughness_raw, raw.loyalty_raw):
        if v and str(v).isdigit():
            nums.add(int(v))
    return {n for n in nums if n >= 2}


def _tree_numbers(node: Any) -> Iterator[int]:
    """The QConst values of a subtree, its costs left out (the costs check reads those)."""
    if isinstance(node, QConst):
        yield node.value
    elif type(node).__name__ == "Cost" or isinstance(node, BackFace):
        return
    elif isinstance(node, AtomArgs):
        for _, value in node.pairs:
            yield from _tree_numbers(value)
    elif dataclasses.is_dataclass(node) and not isinstance(node, type):
        for f in dataclasses.fields(node):
            yield from _tree_numbers(getattr(node, f.name))
    elif isinstance(node, (tuple, list, frozenset)):
        for item in node:
            yield from _tree_numbers(item)


def amounts(raw: RawCard, card: CardRecord) -> list[str]:
    extra = sorted({n for n in _tree_numbers(_front(card)) if isinstance(n, int) and n >= 2} - printed_numbers(raw))
    if not extra:
        return []
    return [(f"the tree holds {extra} but the text never prints {'it' if len(extra) == 1 else 'them'}: "
             "check every amount, count and P/T change (an amount one too high is the commonest plant)")]


# ----------------------------------------------------------------------------- carrier
def _control_aura(card: CardRecord, effect: Any) -> bool:
    """The compiler's one carrier effect, "You control enchanted creature." (B4-gain-control-
    enchanted): GAIN_CONTROL of what the Aura enchants, anchored to the Aura by the engine
    (verbs.py ``_v_gain_control``); M21 Enthralling Hold's verifier recorded its weaker-only gap."""
    return ("Aura" in card.subtypes and isinstance(effect, Atom) and effect.verb is Verb.GAIN_CONTROL
            and any(isinstance(n, FAtom) and n.pred is FAtomPred.IS_ATTACHED_TO_SOURCE
                    for n in walk(effect.args.get("target"))))


def carrier(raw: RawCard, card: CardRecord) -> list[str]:
    if "Land" in card.types or card.is_token or not any(t in card.types for t in _PERMANENT_TYPES):
        return []
    found = []
    for ability in _front(card):
        if isinstance(ability, SpellAbility) and ability.effect is not None and not _control_aura(card, ability.effect):
            found.append(f"the {ability.kind.name.lower()} spell's carrier holds an effect, which happens "
                         "when the card is cast: a permanent spell's text works from the battlefield "
                         "(put it in a triggered, static or activated ability)")
    return found


LINTS = {"players": players, "costs": costs, "amounts": amounts, "carrier": carrier}


def lint(raw: RawCard, card: CardRecord) -> list[str]:
    """Every finding, ``"<lint>: <finding>"``, the listed exceptions left out."""
    out = []
    for name, check in LINTS.items():
        if (name, raw.identity.oracle_id) in EXCEPTIONS:
            continue
        out += [f"{name}: {f}" for f in check(raw, card)]
    return out
