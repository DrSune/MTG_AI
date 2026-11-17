"""Static checks of a card's tree against its printed text, for the defect classes the onboarding
waves found most often (KNOWLEDGE/2026-11-14/207). They run inside gate G0, so a mapper sees them at
``cardtool try`` and ``write``, and ``cardtool verify`` refuses a card that fails one.

- ``players``: who acts or whose objects (29 of 75 planted faults; FDN Pilfer's first record wrote
  "target opponent" as any player, M21 Necromentia gave the caster the Zombies). An opponent-side
  player in the tree needs opponent wording in the text, and the reverse; a designated player
  needs its own words ("target player", "target opponent"); "<subject> <verb>s" needs an atom of
  that verb acting for that side, and one at all (M21 Peer into the Abyss lost its life loss).
- ``costs``: every printed activated ability's cost ("{3}{U}, {T}, Sacrifice this creature:",
  "Equip {3}", "[+1]:"; since ontology round R11 also "Exile this creature", "Exile two cards from
  your graveyard", "Remove a +1/+1 counter from this creature") equals a top-level activated
  ability's cost, part for part, and the tree has no activation the text does not print (6 of 75
  plants; M21 Azusa's land plays as a free activation, which the network used nine times a turn).
- ``amounts``: no number of two or more in the tree that the text never prints (an amount one
  too high is the commonest plant, 25 of 75).
- ``carrier``: a permanent card's cast carrier holds no effect: an effect there happens when the
  card is CAST (the orphaned "If you do, draw a card." of 23 partly compiled cards, M20 Keldon
  Raider; M20 Sorin, Vampire Lord gaining 4 life as it was cast).
- ``food``, ``two_events``, ``its_controller``: the three mapping rulings of
  KNOWLEDGE/2026-11-17/209 §3 (docs/MAPPER_GUIDE.md "Rulings"), each refusing the encodings
  other than its one form: a Food token is ``templates.food_token()``; "When this creature enters
  or dies" is two adjacent triggered abilities with one effect; "N damage to that creature's
  controller" is the referent read over the players, and "its controller" names a target only
  where its ability designates one.
- ``designation``: a population ("creatures you control gain hexproof", a referent-free ALL in
  the ``target`` role) beside a designation in one ability, where the engine reads the
  designation instead (selectors.role_handles reads the binding first; mapper M6's repro).

Each check returns plain-language findings; an empty list is a pass. ``EXCEPTIONS`` lists the
justified exceptions by oracle id, each with its reason. Over every verified card of M21, M20 and
FDN they find nothing but the one listed exception (``test_lints.py``).
"""

from __future__ import annotations

import dataclasses
import re
from collections import Counter
from collections.abc import Iterator
from itertools import pairwise
from typing import Any

from MTG_bot.core.ability_tree import (
    DESIGNATED_PLAYER_REFS,
    QX,
    ActivatedAbility,
    Atom,
    AtomArgs,
    BackFace,
    CardRecord,
    Choose,
    ControllerRef,
    CostExile,
    CostLife,
    CostLoyalty,
    CostManaColor,
    CostManaGeneric,
    CostManaHybrid,
    CostRemoveCounter,
    CostSacrifice,
    CostTap,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DelayedTrigger,
    EachPlayer,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    QConst,
    QPartyCount,
    QUnbounded,
    ReplacementAbility,
    Selector,
    SelectorMode,
    SpellAbility,
    StaticAbility,
    TokenSpec,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    own_nodes,
    walk,
)
from MTG_bot.core.compiler.ingest import RawCard
from MTG_bot.core.compiler.templates import food_token
from MTG_bot.core.executor.selectors import _filter_has_referent, graveyard_sweep_shape

#: (lint, oracle id) -> why the finding is right to ignore. Add one only with the reason, and say
#: so in the card's review; a lint that needs many is a wrong lint.
EXCEPTIONS: dict[tuple[str, str], str] = {
    ("players", "93cf50cf-0ecc-4d3e-abea-778c1ebacec4"): (
        "Massacre Wurm (M21, FDN): \"that creature's controller loses 2 life\" is the last "
        "TARGET_PLAYER antecedent, divergence D18 (docs/ATOM_DIVERGENCES.md); its fold to "
        "Selector(referent='event') is scheduled (BACKLOG B-114), and "
        "tools/audit/test_ontology_conformance.py flags the same card"),
}

#: (oracle id, printed sentence) -> why: sentences labelled inert for good, which no tree holds
#: (docs/MAPPER_GUIDE.md "Labelled sentences"). G0's clause trace accepts the label "inert" on
#: these only, and ``costs`` reads no activation from them. Add one only by a ruling.
INERT: dict[tuple[str, str], str] = {
    ("3e83dec6-e1a0-4137-aaab-308dfd3122e1",
     "[−5]: You may reveal a creature card you own from outside the game and put it into your hand."): (
        "M20 Vivien, Arkbow Ranger: no card is outside the game in self-play or Commander (no "
        "sideboard), so the ability reveals nothing (CR 400.11; the coordinator's ruling, "
        "2026-11-17, KNOWLEDGE/2026-11-17/209 §5)"),
}

OPPONENT_SIDE = frozenset({ControllerRef.OPPONENT, ControllerRef.ALL_OPPONENTS,
                           ControllerRef.TARGET_OPPONENT, ControllerRef.DEFENDING_PLAYER})
_OPPONENT_WORDS = re.compile(r"\bopponents?\b|\bopponent's\b|\bdon't control\b|\bdoesn't control\b"
                             r"|\bdefending player\b", re.IGNORECASE)
_PERMANENT_TYPES = ("Creature", "Artifact", "Enchantment", "Planeswalker", "Battle")


def rules_sentence(raw: RawCard, sentence: str) -> str:
    """One sentence as the lints read it: reminder text left out, the card's own name as ``~``."""
    name = raw.identity.name
    short = name.split(",")[0]
    s = re.sub(r"\s*\([^)]*\)", "", sentence).strip().replace(name, "~")
    return s.replace(short, "~") if short != name and len(short) > 3 else s


def rules_text(raw: RawCard) -> list[str]:
    """The front face's rules sentences (``rules_sentence``), empty ones left out."""
    return [s for s in (rules_sentence(raw, x) for x in raw.sentences) if s]


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
    "mill": (Verb.MOVE_ZONE,),
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
    return atom.verb is Verb.MOVE_ZONE and str(atom.args.get("journal_kind")) == "MILL"


def _performs(stem: str, verb: Verb, atom: Atom) -> bool:
    if verb not in _VERBS[stem]:
        return False
    if stem == "discard" and verb is Verb.MOVE_ZONE:
        return _is_discard(atom)
    if stem == "mill":
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
_COUNT = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10}
#: A printed counter's name as its CounterKind ("charge" is CHARGE).
_KINDS = {"+1/+1": "PLUS_1_PLUS_1", "-1/-1": "MINUS_1_MINUS_1"}


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
        elif re.fullmatch(r"exile (this|~)\b.*", low):
            parts["exile:self"] += 1
        elif m := re.fullmatch(r"exile (\w+) [\w ]*?cards? from your graveyard", low):
            parts[f"exile:{_COUNT.get(m.group(1), m.group(1))}"] += 1
        elif m := re.fullmatch(r"remove (\w+) (\S+) counters? from (?:~|this \w+)", low):
            kind = _KINDS.get(m.group(2), m.group(2).upper())
            parts[f"remove:{kind}:{_COUNT.get(m.group(1), m.group(1))}"] += 1
        else:
            return None  # return, put counters, ...: not read here
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
        elif isinstance(part, CostExile):  # ontology R11: the source, or N cards from a graveyard
            self_ = any(isinstance(c, FAtom) and c.pred is FAtomPred.IS_SOURCE
                        for c in _conjuncts(part.target.filter))
            parts["exile:self" if self_ else f"exile:{part.target.count.value}"] += 1
        elif isinstance(part, CostRemoveCounter):
            parts[f"remove:{part.counter_kind.name}:{part.count.value}"] += 1
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
    inert = {s for oid, s in INERT if oid == raw.identity.oracle_id}
    printed = [(s, p) for s, p in printed_activations(raw) if s not in inert]
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


def _tree_numbers(node: Any) -> Iterator[int | tuple[int, ...]]:
    """The QConst values of a subtree, its costs left out (the costs check reads those), and the
    one Food token's (its "You gain 3 life" is reminder text; ``food`` checks the whole token),
    each as the numbers the text may print for it: a negated comparison at N is "N - 1 or less"
    (CR 107.1) or "unless ... N or more", and "a full party" is a party of four (CR 700.8), which
    prints none."""
    compared = node.inner if isinstance(node, FNot) else node
    if isinstance(compared, FAtom) and compared.pred is FAtomPred.QTY_GE:
        n = compared.count.value if isinstance(compared.count, QConst) else None
        if n is None:
            yield from _tree_numbers(compared.count)
        elif not (isinstance(compared.quantity, QPartyCount) and n == 4):
            yield (n - 1, n) if compared is not node else n
        yield from _tree_numbers(compared.quantity)
        return
    if isinstance(node, QConst):
        yield node.value
    elif (type(node).__name__ == "Cost" or isinstance(node, BackFace)
          or (isinstance(node, TokenSpec) and node == FOOD)):
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
    printed = printed_numbers(raw)
    extra = sorted({
        max(options) for item in _tree_numbers(_front(card))
        for options in [item if isinstance(item, tuple) else (item,)]
        if not any(n < 2 or n in printed for n in options)
    })
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


# ----------------------------------------------------------------------------- the 209 rulings
#: R_FOOD: the one Food token (docs/MAPPER_GUIDE.md "Food tokens").
FOOD = food_token()
_CREATES_FOOD = re.compile(r"\bcreates?\b[^.]*\bFood tokens?\b", re.IGNORECASE)


def food(raw: RawCard, card: CardRecord) -> list[str]:
    """Every Food token in the tree (any face) is ``FOOD``, and a front face that creates one
    holds a CREATE_TOKEN of it."""
    found = []
    odd = [n for n in walk(card) if isinstance(n, TokenSpec)
           and (n.name == "Food" or "Food" in n.subtypes) and n != FOOD]
    if odd:
        found.append(f"{len(odd)} Food TokenSpec(s) differ from the one Food (MAPPER_GUIDE 'Food "
                     "tokens', templates.food_token()): copy it exactly, subtype Food and no keyword")
    makes = any(isinstance(n, Atom) and n.verb is Verb.CREATE_TOKEN and n.args.get("tokens") == FOOD
                for a in _front(card) for n in walk(a))
    if any(_CREATES_FOOD.search(s) for s in rules_text(raw)) and not makes:
        found.append("the text creates a Food token, but no CREATE_TOKEN in the tree makes the one Food")
    return found


#: R_TWOEVENTS: "When this creature enters or dies, <effect>" (and "enters or attacks", "attacks
#: or blocks") is two triggered abilities, adjacent in printed order, each with the compiler's own
#: event for its half and one condition and one effect: the form the compiler gives M21 Elder
#: Gargaroth's "attacks or blocks" (docs/MAPPER_GUIDE.md "One trigger, two events").
_TWO_EVENTS = re.compile(r"^(?:When|Whenever) (?:this \w+|~) (enters|attacks) or (dies|attacks|blocks), ",
                         re.IGNORECASE)
_SELF = FAtom(pred=FAtomPred.IS_SOURCE)
SELF_EVENTS = {
    "enters": ZoneChangeEvent(from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
                              to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU), subject=_SELF),
    "dies": CreatureDiesEvent(filter=_SELF),
    "attacks": DeclareAttackersEvent(filter=_SELF),
    "blocks": DeclareBlockersEvent(filter=_SELF),
}


def two_events(raw: RawCard, card: CardRecord) -> list[str]:
    tops = _front(card)
    found = []
    for s in rules_text(raw):
        m = _TWO_EVENTS.match(s)
        if m is None:
            continue
        first, second = (SELF_EVENTS[w.lower()] for w in m.groups())
        if not any(isinstance(a, TriggeredAbility) and isinstance(b, TriggeredAbility)
                   and (a.event, b.event) == (first, second)
                   and (a.condition, a.effect, a.once_per_event) == (b.condition, b.effect, b.once_per_event)
                   for a, b in pairwise(tops)):
            found.append(f'"{s[:60]}": two triggered abilities, adjacent and in printed order, with '
                         f"one condition and one effect: {type(first).__name__} then "
                         f"{type(second).__name__}, each as the compiler writes \"this creature\"'s")
    return found


#: R_ITSCONTROLLER: "N damage to that creature's controller" is DEAL_DAMAGE over every player who
#: controls the referent (M20 Chandra, Flame's Fury's verified -2; docs/MAPPER_GUIDE.md "That
#: creature's controller").
_DAMAGE_TO_CONTROLLER = re.compile(
    r"\bdamage to (?:that (?:creature|land|artifact|enchantment|permanent|planeswalker)'s|its) "
    r"controller\b", re.IGNORECASE)


def controller_of_referent(referent: str) -> Selector:
    """The players "that creature's controller" names: CONTROLLER_IS of the referent object."""
    return Selector(
        count=QUnbounded(), mode=SelectorMode.ALL,
        filter=FAtom(pred=FAtomPred.CONTROLLER_IS, who=Selector(
            count=QConst(1), mode=SelectorMode.CHOOSE, filter=FAnd(()),
            zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),), referent=referent)),
        zones=(Zone(ZoneKind.PLAYER, ControllerRef.ANY),))


_RECIPIENTS = (controller_of_referent("target"), controller_of_referent("event"))
_ABILITIES = (TriggeredAbility, ActivatedAbility, SpellAbility, DelayedTrigger, StaticAbility,
              ReplacementAbility)


def _own(ability: Any) -> list[Any]:
    """An ability and the nodes of its body that are its own (``own_nodes``: not a granted,
    token or delayed ability's)."""
    body = ability.action if isinstance(ability, ReplacementAbility) else ability.effect
    return [ability, *(own_nodes(body) if body is not None else ())]


def _designates(nodes: list[Any]) -> bool:
    """The ability's own nodes choose a target: a TARGET-mode selector of its own, or a
    designated player anywhere (CR 115.1)."""
    for n in nodes:
        if isinstance(n, Selector) and n.mode is SelectorMode.TARGET and n.referent is None:
            return True
        values = n.pairs if isinstance(n, AtomArgs) else [getattr(n, f.name) for f in dataclasses.fields(n)]
        flat = [v for pair in values for v in (pair if isinstance(pair, tuple) else (pair,))]
        if any(isinstance(v, ControllerRef) and v in DESIGNATED_PLAYER_REFS for v in flat):
            return True
    return False


def _player_referents(nodes: list[Any]) -> Iterator[Selector]:
    """The referent Selectors read as a player ("its controller"): CONTROLLER_IS's ``who``, a
    ``controller`` role, an EachPlayer's ``ref``."""
    for n in nodes:
        if isinstance(n, FAtom) and n.pred is FAtomPred.CONTROLLER_IS:
            who = n.who
        elif isinstance(n, Atom):
            who = n.args.get("controller")
        elif isinstance(n, EachPlayer):
            who = n.ref
        else:
            continue
        if isinstance(who, Selector) and who.referent is not None:
            yield who


def its_controller(raw: RawCard, card: CardRecord) -> list[str]:
    found = []
    printed = sum(len(_DAMAGE_TO_CONTROLLER.findall(s)) for s in rules_text(raw))
    held = sum(1 for a in _front(card) for n in walk(a) if isinstance(n, Atom)
               and n.verb is Verb.DEAL_DAMAGE and n.args.get("target") in _RECIPIENTS)
    if held < printed:
        found.append(f"{printed} \"damage to that creature's controller\" in the text, {held} in the tree: "
                     "DEAL_DAMAGE over Zone(PLAYER, ANY) with CONTROLLER_IS of the referent (never a "
                     "TARGET slot over the players, the recipient role, TARGET_PLAYER or EachPlayer)")
    for ability in (n for a in _front(card) for n in walk(a) if isinstance(n, _ABILITIES)):
        nodes = _own(ability)
        if not _designates(nodes) and any(s.referent == "target" for s in _player_referents(nodes)):
            found.append(f"a {type(ability).__name__} reads \"its controller\" of a target it never "
                         "chooses: name the event's object (referent 'event') or the ability's own "
                         "target; a damage trigger's dealer is no referent (KNOWLEDGE 203)")
    return found


# ----------------------------------------------------------------------------- designation
def _scopes(ability: Any) -> list[list[Any]]:
    """The node sets one designation is bound across (the ``target`` binding): the ability's
    own nodes, or for a "choose one" each mode's, since only the chosen mode designates (CR
    601.2b-c; stack._plan_cast_designation, binding._declare_mode). Modes chosen together
    ("choose two") share one."""
    body = ability.action if isinstance(ability, ReplacementAbility) else ability.effect
    if isinstance(body, Choose) and body.count == QConst(1):
        return [[ability, *own_nodes(option)] for option in body.options]
    return [_own(ability)]


def _population_reads_designation(atom: Atom) -> bool:
    """An ALL Selector in the atom's ``target`` role that ``selectors.role_handles`` resolves
    from the designation bound under that role, never itself: no referent of its own or in its
    filter, not a player zone alone, not the whole-graveyard sweep (its exemptions)."""
    value = atom.args.get("target")
    return (isinstance(value, Selector) and value.mode is SelectorMode.ALL and value.referent is None
            and not (len(value.zones) == 1 and value.zones[0].kind is ZoneKind.PLAYER)
            and not _filter_has_referent(value.filter)
            and not graveyard_sweep_shape(value, atom.verb, atom.args.get("destination")))


def _binds_players_only(ability: Any, nodes: list[Any]) -> bool:
    """Every object the scope designates is a player: its targets are over player zones, and it
    is no damage or dies trigger reading "that player" with no printed target, which binds the
    dealer or the dead creature, a card (binding.TriggerBinder._put)."""
    targets = [n for n in nodes if isinstance(n, Selector) and n.mode is SelectorMode.TARGET and n.referent is None]
    if any(z.kind is not ZoneKind.PLAYER for t in targets for z in t.zones):
        return False
    return targets or not (isinstance(ability, TriggeredAbility)
                           and isinstance(ability.event, (DamageDealtEvent, CreatureDiesEvent)))


def designation(raw: RawCard, card: CardRecord) -> list[str]:
    """One tree shape, two meanings: a referent-free ALL in the ``target`` role is a population
    ("creatures you control gain hexproof"), but beside a designation ``role_handles`` reads the
    designation instead (binding first; the payments' ``all_bf()`` idiom needs it), so the effect
    acts on the designated object only (BACKLOG, the "Up to" entry; mapper M6's repro). A card
    population beside designated players resolves itself (role_handles' player_into_cards)."""
    found = []
    for ability in (n for a in _front(card) for n in walk(a) if isinstance(n, _ABILITIES)):
        for nodes in _scopes(ability):
            if not _designates(nodes):
                continue
            players = _binds_players_only(ability, nodes)
            for atom in nodes:
                if not (isinstance(atom, Atom) and _population_reads_designation(atom)):
                    continue
                zones = atom.args.get("target").zones
                if players and all(z.kind not in (ZoneKind.PLAYER, ZoneKind.ANY) for z in zones):
                    continue
                found.append(f"a {type(ability).__name__} designates a target, and its {atom.verb.name} over "
                             "every object of a population (ALL, no referent) in the target role would act on "
                             "that designation instead: no encoding gives a population beside a designation "
                             "yet, so record needs-atom (\"ENGINE: ...\")")
    return found


LINTS = {"players": players, "costs": costs, "amounts": amounts, "carrier": carrier,
         "food": food, "two_events": two_events, "its_controller": its_controller,
         "designation": designation}


def lint(raw: RawCard, card: CardRecord) -> list[str]:
    """Every finding, ``"<lint>: <finding>"``, the listed exceptions left out."""
    out = []
    for name, check in LINTS.items():
        if (name, raw.identity.oracle_id) in EXCEPTIONS:
            continue
        out += [f"{name}: {f}" for f in check(raw, card)]
    return out
