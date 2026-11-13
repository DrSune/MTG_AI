"""Package mode (docs/PLAN_CEILING.md §14.1, §14.3): decks that carry a synergy package.

A package is the consumers of an event or a property together with the producers that cause it.
Both are read off the compiled ability trees (MTG_bot/core/ability_tree.py), never off card
names, so a new set's packages need no code (NORTH_STAR rank 1, tied). The derivation table,
one row per family (``EVENTS``, ``PREDICATES``, ``_static_shapes``, ``_count_shape``; ``ACTS``):

| family    | a consumer reads                                         | a producer is            |
|-----------|----------------------------------------------------------|--------------------------|
| spell     | CastSpellEvent(by you, F); INSTANT_OR_SORCERY_CAST_      | a nonland card F holds   |
|           | THIS_TURN(you) (F = instant or sorcery); QCount(F in     | for                      |
|           | your graveyard). A TURN_OF(opponent) condition adds      |                          |
|           | instant speed to F (CR 307.1)                            |                          |
| permanent | ZoneChangeEvent(to your battlefield, F); DeclareAttack-  | a permanent card, or a   |
|           | ersEvent(F, yours); AbilityTriggerEvent(F, yours); a     | token it creates, F      |
|           | static's MODIFY_PT / GRANT_ABILITY over Sel[ALL F,       | holds for (a basic land  |
|           | yours]; CONTROLLER_COUNT_GE(F); QCount(F, yours)         | is in every deck)        |
| life      | LifeGainedEvent(by you); LIFE_GAINED_THIS_TURN_GE(you)   | GAIN_LIFE for you;       |
|           |                                                          | LIFELINK                 |
| draw      | CardDrawnEvent(by you); CARDS_DRAWN_THIS_TURN_GE(you)    | DRAW for you             |
| sacrifice | SacrificeEvent(by you)                                   | CostSacrifice; SACRIFICE |
| dies      | CreatureDiesEvent(yours)                                 | a CostSacrifice or       |
|           |                                                          | SACRIFICE of a creature  |
| counter   | CounterPlacedEvent(+1/+1, yours); HAS_COUNTER(+1/+1)     | PUT_COUNTER(+1/+1)       |
| burn      | DamageDealtEvent(to an opponent, noncombat)              | DEAL_DAMAGE that can hit |
|           |                                                          | an opponent              |
| mill      | ZONE_COUNT_GE(an opponent's graveyard)                   | MOVE_ZONE MILL by an     |
|           |                                                          | opponent                 |

"You" is the ability's controller, except inside EachPlayer over the opponents. A trigger on the
source itself (IS_SOURCE, IS_ATTACHED_TO_SOURCE) consumes nothing other cards make, and an event
class or predicate outside the table is skipped. F is read against a card's printed
characteristics (or a token's) in three values, a predicate of the game state being unknown,
and only "true" makes a producer. Consumers fed by the same producers are one package.

Construction (``package_decks``), per deck from the deal's seed: a package, then the colour pair
holding the most of its consumers and then the most producer copies; up to
``CONSUMER_COPIES`` consumers and ``PRODUCER_COPIES`` producers (basic producers count), the rest
filled as ``games.build_coherent_deck`` fills, with its 24 basics and MAX_COPIES. A package with
no pair holding one consumer and ``PRODUCER_COPIES`` producer copies is dropped (``derive``).

    .venv/bin/python -m tools.selfplay.packages M21 M20 FDN [--pool verified]
"""

from __future__ import annotations

import argparse
import dataclasses
import random
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from MTG_bot.core.ability_tree import (
    AbilityTriggerEvent,
    ActivatedAbility,
    Atom,
    BackFace,
    CardDrawnEvent,
    CardRecord,
    CastSpellEvent,
    ControllerRef,
    CostModifier,
    CostSacrifice,
    CounterKind,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DelayedTrigger,
    EachPlayer,
    EmblemSpec,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    KickerAbility,
    LifeGainedEvent,
    QConst,
    QCount,
    ReplacementAbility,
    SacrificeEvent,
    Selector,
    SelectorMode,
    SpellAbility,
    StaticAbility,
    TokenSpec,
    TriggeredAbility,
    Verb,
    ZoneChangeEvent,
    ZoneKind,
    canonical_json,
    walk,
)
from MTG_bot.core.executor.games import COHERENT_LANDS, DECK_SIZE, MAX_COPIES
from MTG_bot.core.executor.quantity import _PERMANENT_TYPE_WORDS, _type_line_tokens

DEAL_SEED = 1409  # rig.play_game's deck_pairs_seed (decks.DEAL_SEED)
#: SCAFFOLD (docs/BACKLOG.md "Package decks"): a player has seen 16 cards of 60 by their ninth
#: turn (an 18-turn game), so 8 copies of a kind are seen in 93% of games and 4 in 72%. A
#: package deck holds 8 consumer copies (4 with one consumer in the pair) and 8 producer copies
#: besides them; a consumer that also produces counts toward a pair's 8 producer copies.
CONSUMER_COPIES = 8
PRODUCER_COPIES = 8
PAIRS = tuple("".join(p) for p in combinations("BGRUW", 2))  # build_coherent_deck's sorted pairs

P = FAtomPred
YOU, OPPONENT, ANY = ControllerRef.YOU, ControllerRef.OPPONENT, ControllerRef.ANY
_OPPONENTS = frozenset({OPPONENT, ControllerRef.ALL_OPPONENTS, ControllerRef.TARGET_OPPONENT,
                        ControllerRef.DEFENDING_PLAYER})
_ABILITIES = (StaticAbility, TriggeredAbility, ActivatedAbility, SpellAbility, KeywordAbility,
              ReplacementAbility, CostModifier, EtBState, KickerAbility)
_NESTED = (*_ABILITIES, TokenSpec, EmblemSpec, DelayedTrigger, BackFace)

Shape = tuple[str, Any]  # (family, the subject filter for spell and permanent, else None)


# ---------------------------------------------------------- a filter against printed characteristics

@dataclass(frozen=True)
class Obj:
    """What a subject filter is read against: a card as printed, a token as created, a player.
    ``words`` are its type line's words, which TYPE_EQ, SUBTYPE_EQ and SUPERTYPE_EQ all read
    (as quantity.eval_filter does)."""

    words: frozenset[str]
    colors: frozenset[str] = frozenset()
    keywords: frozenset[Keyword] = frozenset()
    power: int | None = None
    mana_value: int = 0
    token: bool = False

    @property
    def permanent(self) -> bool:
        return bool(self.words & _PERMANENT_TYPE_WORDS)


def _int(q: Any) -> int | None:
    return q.value if isinstance(q, QConst) else None


def card_obj(rec: CardRecord) -> Obj:
    kw = {k.keyword for k in rec.keywords} | {a.keyword for a in rec.abilities
                                               if isinstance(a, KeywordAbility)}
    return Obj(frozenset(_type_line_tokens(rec.type_line)), frozenset(rec.colors),
               frozenset(kw), _int(rec.power), rec.mana_value)


def token_obj(spec: TokenSpec) -> Obj:
    kw = set(spec.keywords) | {a.keyword for a in spec.abilities if isinstance(a, KeywordAbility)}
    return Obj(frozenset(_type_line_tokens(spec.type_line)), frozenset(spec.colors),
               frozenset(kw), _int(spec.power), 0, True)


def _cmp(value: int | None, q: Any, ge: bool) -> bool | None:
    n = _int(q)
    return None if value is None or n is None else (value >= n if ge else value <= n)


#: The predicates of printed characteristics; any other one is unknown (None). A producer is
#: yours and is not the consumer (IS_SOURCE).
_READ = {
    P.TYPE_EQ: lambda a, o: a.string_value in o.words,
    P.SUBTYPE_EQ: lambda a, o: a.string_value in o.words,
    P.SUPERTYPE_EQ: lambda a, o: a.string_value in o.words,
    P.COLOR_HAS: lambda a, o: a.color in o.colors,
    P.KEYWORD_HAS: lambda a, o: a.keyword in o.keywords,
    P.POWER_GE: lambda a, o: _cmp(o.power, a.count, True),
    P.POWER_LE: lambda a, o: _cmp(o.power, a.count, False),
    P.CMC_GE: lambda a, o: _cmp(o.mana_value, a.count, True),
    P.CMC_LE: lambda a, o: _cmp(o.mana_value, a.count, False),
    P.IS_TOKEN: lambda a, o: o.token,
    P.IS_PERMANENT: lambda a, o: o.permanent,
    P.IS_SOURCE: lambda a, o: False,
    P.CONTROLLER_IS: lambda a, o: {YOU: True, OPPONENT: False}.get(a.who),
}


def holds(f: Any, o: Obj) -> bool | None:
    """``f`` read against ``o`` in three values (None: it reads something unknown)."""
    if f is None:
        return True
    if isinstance(f, (FAnd, FOr)):
        vals = {holds(c, o) for c in f.children}
        stop = isinstance(f, FOr)  # the value that decides: True for an or, False for an and
        return stop if stop in vals else (None if None in vals else not stop)
    if isinstance(f, FNot):
        v = holds(f.inner, o)
        return None if v is None else not v
    read = _READ.get(f.pred)
    return None if read is None else read(f, o)


_CREATURE = Obj(frozenset({"Creature"}))  # some creature of yours, nothing else known
_PLAYER = Obj(frozenset({"Player"}))  # query.py's "any target": TYPE_EQ Player
_INSTANT_SPEED = FOr((FAtom(P.TYPE_EQ, string_value="Instant"),
                      FAtom(P.KEYWORD_HAS, keyword=Keyword.FLASH)))
_INSTANT_OR_SORCERY = FOr((FAtom(P.TYPE_EQ, string_value="Instant"),
                           FAtom(P.TYPE_EQ, string_value="Sorcery")))
_OPPONENTS_TURN = FAtom(P.TURN_OF, who=OPPONENT)


# ------------------------------------------------------------------------------------ consumers

def _conj(f: Any) -> tuple:
    return f.children if isinstance(f, FAnd) else (f,)


def _names(f: Any, pred: FAtomPred, who: Any = None) -> bool:
    """Is ``pred`` (with ``who``) one of the conjuncts of ``f``?"""
    return any(isinstance(c, FAtom) and c.pred is pred and (who is None or c.who is who)
               for c in _conj(f))


def _by_you(actor: Any) -> bool:
    return actor is None or _names(actor, P.CONTROLLER_IS, YOU)


def _other_of_yours(f: Any) -> bool:
    """A subject of yours that can be another object than the ability's source."""
    return (f is not None and _names(f, P.CONTROLLER_IS, YOU)
            and not (_names(f, P.IS_SOURCE) or _names(f, P.IS_ATTACHED_TO_SOURCE)))


#: A trigger's event class -> the shape it consumes; None: not one other cards feed.
EVENTS = {
    CastSpellEvent: lambda e: ("spell", e.filter) if _by_you(e.actor) else None,
    ZoneChangeEvent: lambda e: ("permanent", e.subject) if (
        e.to_zone.kind is ZoneKind.BATTLEFIELD and e.to_zone.controller is YOU
        and e.subject is not None and not _names(e.subject, P.IS_SOURCE)) else None,
    DeclareAttackersEvent: lambda e: ("permanent", e.filter) if _other_of_yours(e.filter) else None,
    AbilityTriggerEvent: lambda e: ("permanent", e.filter) if _other_of_yours(e.filter) else None,
    LifeGainedEvent: lambda e: ("life", None) if _by_you(e.actor) else None,
    CardDrawnEvent: lambda e: ("draw", None) if _by_you(e.actor) else None,
    SacrificeEvent: lambda e: ("sacrifice", None) if _by_you(e.actor) else None,
    CreatureDiesEvent: lambda e: ("dies", None) if _other_of_yours(e.filter) else None,
    CounterPlacedEvent: lambda e: ("counter", None) if (
        e.counter_kind is CounterKind.PLUS_1_PLUS_1 and _other_of_yours(e.filter)) else None,
    DamageDealtEvent: lambda e: ("burn", None) if (
        e.combat is False and _names(e.filter, P.OPPONENT_OF)) else None,
}


def event_shape(event: Any) -> Shape | None:
    return EVENTS.get(type(event), lambda e: None)(event)


#: A keyword the engine expands into a trigger (binding.py ``_keyword_node``) -> its shape.
KEYWORDS = {Keyword.PROWESS: ("spell", FNot(FAtom(P.TYPE_EQ, string_value="Creature")))}


#: A predicate of a property counted in play -> the shape it consumes.
PREDICATES = {
    P.LIFE_GAINED_THIS_TURN_GE: lambda a: ("life", None) if a.who is YOU else None,
    P.CARDS_DRAWN_THIS_TURN_GE: lambda a: ("draw", None) if a.who is YOU else None,
    P.INSTANT_OR_SORCERY_CAST_THIS_TURN: lambda a: (
        ("spell", _INSTANT_OR_SORCERY) if a.who is YOU else None),
    P.CONTROLLER_COUNT_GE: lambda a: ("permanent", a.inner_filter),
    P.HAS_COUNTER: lambda a: ("counter", None) if a.counter_kind is CounterKind.PLUS_1_PLUS_1
    else None,
    P.ZONE_COUNT_GE: lambda a: ("mill", None) if (
        a.who is OPPONENT and a.zone.kind is ZoneKind.GRAVEYARD) else None,
    P.EVENT_THIS_TURN: lambda a: event_shape(a.event),
}


def _count_shape(q: QCount) -> Shape | None:
    zones = {(z.kind, z.controller) for z in q.selector.zones}
    if (ZoneKind.GRAVEYARD, YOU) in zones:
        return "spell", q.selector.filter
    if any(k is ZoneKind.BATTLEFIELD for k, _ in zones) and _other_of_yours(q.selector.filter):
        return "permanent", q.selector.filter
    return None


def _static_shapes(atom: Atom) -> Shape | None:
    """A static's MODIFY_PT or GRANT_ABILITY over all of your permanents that F picks."""
    sel = atom.args.get("target")
    if (atom.verb in (Verb.MODIFY_PT, Verb.GRANT_ABILITY) and isinstance(sel, Selector)
            and sel.mode is SelectorMode.ALL and _other_of_yours(sel.filter)):
        return "permanent", sel.filter
    return None


def _children(node: Any) -> Iterator[Any]:
    """The tree nodes directly below ``node`` (its fields, tuples and sets opened)."""
    stack = [getattr(node, f.name) for f in dataclasses.fields(node)]
    while stack:
        v = stack.pop()
        if isinstance(v, (tuple, frozenset)):
            stack.extend(v)
        elif dataclasses.is_dataclass(v) and not isinstance(v, type):
            yield v


def _own(node: Any) -> Iterator[Any]:
    """The nodes below an ability that are its own: not those of an ability or token in it."""
    for c in _children(node):
        yield c
        if not isinstance(c, _NESTED):
            yield from _own(c)


def shapes(ability: Any) -> set[Shape]:
    """What one ability consumes (not the abilities nested in it). A negated predicate ("if you
    didn't cast a spell this turn") wants the property absent, so it is no consumer."""
    out: set[Shape | None] = set()
    if isinstance(ability, TriggeredAbility):
        s = event_shape(ability.event)
        if s and s[0] == "spell" and ability.condition == _OPPONENTS_TURN:
            s = ("spell", FAnd((s[1], _INSTANT_SPEED)))
        out.add(s)
    elif isinstance(ability, KeywordAbility):
        out.add(KEYWORDS.get(ability.keyword))
    own = list(_own(ability))
    negated = {id(x) for n in own if isinstance(n, FNot) for x in walk(n.inner)}
    for n in own:
        if isinstance(n, FAtom) and n.pred in PREDICATES and id(n) not in negated:
            out.add(PREDICATES[n.pred](n))
        elif isinstance(n, QCount):
            out.add(_count_shape(n))
        elif isinstance(n, Atom) and isinstance(ability, StaticAbility):
            out.add(_static_shapes(n))
    out.discard(None)
    return out  # type: ignore[return-value]


def consumer_shapes(rec: CardRecord) -> set[Shape]:
    """What a card consumes: its abilities', those it grants and its tokens' included."""
    return {s for n in walk(rec, skip=BackFace) if isinstance(n, _ABILITIES) for s in shapes(n)}


# ------------------------------------------------------------------------------------ producers

def _framed(node: Any, opp: bool, src: Obj | None) -> Iterator[tuple[Any, bool, Obj | None]]:
    """Every node with its frame: is "you" there an opponent (inside EachPlayer over the
    opponents, or a token another player creates), and the object IS_SOURCE names (a token in
    its spec; unknown in a grant). A replacement changes an event that happens anyway, so
    nothing below it produces one."""
    if (isinstance(node, EachPlayer) and node.ref in _OPPONENTS
            or _verb(node, Verb.CREATE_TOKEN) and node.args.get("controller") not in (None, YOU)):
        opp = True
    elif isinstance(node, TokenSpec):
        src = token_obj(node)
    elif isinstance(node, Atom) and node.verb is Verb.GRANT_ABILITY:
        src = None
    yield node, opp, src
    if not isinstance(node, (BackFace, ReplacementAbility)):
        for c in _children(node):
            yield from _framed(c, opp, src)


def _for(ref: Any, opp: bool, mine: bool) -> bool:
    """Does a player role name you (``mine``) or an opponent? "Target player" and "any player"
    may name either."""
    if ref in (ANY, ControllerRef.TARGET_PLAYER):
        return True
    if ref is YOU:
        return opp != mine
    return ref in _OPPONENTS and not mine


def _keywords(n: Any) -> set:
    return {n.keyword} if isinstance(n, KeywordAbility) else (
        set(n.keywords) if isinstance(n, TokenSpec) else set())


def _sacrificed(n: Any) -> Selector | None:
    if isinstance(n, CostSacrifice):
        return n.target
    return n.args.get("target") if isinstance(n, Atom) and n.verb is Verb.SACRIFICE else None


def _creature_dies(sel: Selector | None, src: Obj | None) -> bool:
    """Does a sacrifice of ``sel`` kill a creature of yours: "a creature", or "this" creature?"""
    return sel is not None and (holds(sel.filter, _CREATURE) is True or (
        src is not None and "Creature" in src.words and _names(sel.filter, P.IS_SOURCE)))


def _hits_opponent(sel: Any, opp: bool) -> bool:
    """A damage target that can be an opponent: a player zone not yours, or "any target"; not an
    object already bound (a referent: the entering creature, the event's subject)."""
    return isinstance(sel, Selector) and sel.referent is None and any(
        z.controller is not YOU or opp if z.kind is ZoneKind.PLAYER
        else holds(sel.filter, _PLAYER) is True for z in sel.zones)


def _verb(n: Any, verb: Verb) -> bool:
    return isinstance(n, Atom) and n.verb is verb


#: An act family -> is this node, in its frame, one of its producers?
ACTS = {
    "life": lambda n, opp, src: (_verb(n, Verb.GAIN_LIFE) and _for(n.args.get("controller"), opp, True)
                                 or not opp and Keyword.LIFELINK in _keywords(n)),
    "draw": lambda n, opp, src: _verb(n, Verb.DRAW) and _for(n.args.get("controller"), opp, True),
    "sacrifice": lambda n, opp, src: not opp and _sacrificed(n) is not None,
    "dies": lambda n, opp, src: not opp and _creature_dies(_sacrificed(n), src),
    "counter": lambda n, opp, src: (not opp and _verb(n, Verb.PUT_COUNTER)
                                    and n.args.get("counter_kind") is CounterKind.PLUS_1_PLUS_1),
    "burn": lambda n, opp, src: _verb(n, Verb.DEAL_DAMAGE) and _hits_opponent(n.args.get("target"),
                                                                             opp),
    "mill": lambda n, opp, src: (_verb(n, Verb.MOVE_ZONE) and n.args.get("journal_kind") == "MILL"
                                 and _for(n.args.get("controller"), opp, False)),
}


def produces(rec: CardRecord, shape: Shape) -> bool:
    """Does the card (a nonland card or a basic land) cause what ``shape`` reads?"""
    family, f = shape
    me = card_obj(rec)
    if family == "spell":
        return "Land" not in me.words and holds(f, me) is True
    if family == "permanent":
        return (me.permanent and holds(f, me) is True) or any(
            isinstance(n, TokenSpec) and not opp and holds(f, token_obj(n)) is True
            for n, opp, _ in _framed(rec, False, me))
    return any(ACTS[family](n, opp, src) for n, opp, src in _framed(rec, False, me))


# --------------------------------------------------------------------------------- the packages

@dataclass(frozen=True)
class Package:
    shapes: tuple[Shape, ...]  # what its consumers read
    consumers: tuple[str, ...]  # oracle ids, every colour
    producers: tuple[str, ...]  # oracle ids of nonland cards and basic lands, every colour
    pairs: tuple[str, ...]  # the colour pairs holding the most consumers, then producer copies


def _key(shape: Shape) -> tuple[str, str]:
    return shape[0], "" if shape[1] is None else canonical_json(shape[1])


def _text(f: Any) -> str:
    """A subject filter in a few words, "yours" and "another" left out."""
    if isinstance(f, (FAnd, FOr)):
        return ("&" if isinstance(f, FAnd) else "|").join(
            t for t in map(_text, f.children) if t)
    if isinstance(f, FNot):
        inner = _text(f.inner)
        return "" if inner == "IS_SOURCE" else "!" + inner
    if f.pred is P.CONTROLLER_IS:
        return ""
    n = _int(f.count)
    return (f.string_value or (f.keyword and f.keyword.name) or f.color
            or (f"{f.pred.name}{n}" if n is not None else f.pred.name))


def label(pkg: Package) -> str:
    """A package's families and subjects: "life", "permanent[Zombie]", "spell[!Creature]"."""
    return "+".join(sorted({fam if f is None else f"{fam}[{_text(f)}]" for fam, f in pkg.shapes}))


def derive(supply: Any) -> tuple[list[Package], list[tuple[Package, str]]]:
    """The supply's packages, and those dropped with the reason. A pair holds a card whose
    colour identity it covers; a package is kept when one pair holds a consumer and
    PRODUCER_COPIES producer copies (MAX_COPIES of a spell, a consumer that produces included,
    and COHERENT_LANDS / 2 of a basic)."""
    metas = supply.metas
    rec = {c: supply.pool.results[c].card for c in supply.deckable}
    cards = [c for c in supply.deckable if not metas[c].is_land or metas[c].is_basic]
    by_shape: dict[Shape, set[str]] = defaultdict(set)
    for c in cards:
        if not metas[c].is_land:
            for s in consumer_shapes(rec[c]):
                by_shape[s].add(c)
    groups: dict[frozenset[str], tuple[list[Shape], set[str]]] = {}
    for s in sorted(by_shape, key=_key):
        fed = frozenset(c for c in cards if produces(rec[c], s))
        shapes_, cons = groups.setdefault(fed, ([], set()))
        shapes_.append(s)
        cons |= by_shape[s]
    kept, dropped = [], []
    for fed, (shapes_, cons) in groups.items():
        score = {}
        for pair in PAIRS:
            inside = {c for c in cons | fed if rec[c].color_identity <= set(pair)}
            held = len(cons & inside)
            copies = sum(COHERENT_LANDS // 2 if metas[c].is_basic else MAX_COPIES
                         for c in fed & inside)
            if held and copies >= PRODUCER_COPIES:
                score[pair] = (held, copies)
        best = max(score.values(), default=None)
        pkg = Package(tuple(shapes_), tuple(sorted(cons)), tuple(sorted(fed)),
                      tuple(p for p in PAIRS if score.get(p) == best))
        if best is None:
            why = f"no colour pair holds a consumer and {PRODUCER_COPIES} producer copies"
            dropped.append((pkg, why))
        else:
            kept.append(pkg)
    return kept, dropped


_DERIVED: dict[int, tuple[Any, list[Package]]] = {}


def packages(supply: Any) -> list[Package]:
    """The kept packages of a supply, derived once per process (the drops logged to stderr)."""
    if id(supply) not in _DERIVED:
        kept, dropped = derive(supply)
        print(f"packages[{supply.mode}, {len(supply.deckable)} cards]: {len(kept)} kept, "
              f"{len(dropped)} dropped: {', '.join(label(p) for p, _ in dropped)}",
              file=sys.stderr)
        _DERIVED[id(supply)] = (supply, kept)  # the supply pins the id
    return _DERIVED[id(supply)][1]


def build(deck_seed: int, supply: Any, pkgs: list[Package]) -> tuple[Package, tuple[str, ...]]:
    """One package deck and its package: a seeded package and pair, then the module
    docstring's counts."""
    rng = random.Random(deck_seed)
    pkg = pkgs[rng.randrange(len(pkgs))]
    pair = pkg.pairs[rng.randrange(len(pkg.pairs))]
    metas, results = supply.metas, supply.pool.results
    basics = {next(iter(results[c].card.color_identity)): c for c in supply.deckable
              if metas[c].is_basic}
    deck = [basics[pair[i % 2]] for i in range(COHERENT_LANDS)]
    spells = [c for c in supply.deckable
              if not metas[c].is_land and results[c].card.color_identity <= set(pair)]
    copies: Counter = Counter()

    def add(pool: list[str], n: int) -> None:
        pool = [c for c in pool if copies[c] < MAX_COPIES]
        while n > 0 and pool:
            c = pool[rng.randrange(len(pool))]
            copies[c] += 1
            deck.append(c)
            n -= 1
            if copies[c] == MAX_COPIES:
                pool.remove(c)

    add([c for c in spells if c in pkg.consumers], CONSUMER_COPIES)
    fed = set(pkg.producers) - set(pkg.consumers)  # the basics among them are in the deck
    add([c for c in spells if c in fed], PRODUCER_COPIES - sum(c in fed for c in deck))
    add(spells, DECK_SIZE - len(deck))
    rng.shuffle(deck)
    return pkg, tuple(deck)


def package_deal(seed: int, share: float) -> bool:
    """Is this deal one of a ``share`` dealt as package decks (learner --package-share)? Read off
    the deal's seed alone, so both games of an evaluation deal and every evaluation agree."""
    return share > 0 and random.Random(f"package-share:{seed}").random() < share


def package_decks(seed: int, supply: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """A deal's two package decks, from its seed alone (as games.deal_decks)."""
    rng = random.Random(f"package:{DEAL_SEED}:{seed}")
    first, second = (build(rng.randrange(1 << 40), supply, packages(supply))[1] for _ in range(2))
    return first, second


# ------------------------------------------------------------------------------------- report

def report(supply: Any, set_code: str, show: int = 12) -> str:
    """The packages of a pool: consumers, producers per pair, and what was dropped and why."""
    kept, dropped = derive(supply)
    name = {c: supply.metas[c].name for c in supply.deckable}
    rec = {c: supply.pool.results[c].card for c in supply.deckable}
    out = [f"== {set_code} ({supply.mode}): {len(kept)} packages kept, {len(dropped)} dropped"]
    for pkg in kept:
        pair = set(pkg.pairs[0])
        cons = [c for c in pkg.consumers if rec[c].color_identity <= pair]
        fed = [c for c in pkg.producers if rec[c].color_identity <= pair]
        spells = [c for c in fed if c not in pkg.consumers and not supply.metas[c].is_basic]
        basics = sum(supply.metas[c].is_basic for c in fed)
        out.append(f"- {label(pkg)} in {'/'.join(pkg.pairs)}: {len(cons)} of {len(pkg.consumers)} "
                   f"consumers ({sum(c in pkg.producers for c in cons)} of them producers), "
                   f"{len(spells)} other producer spells" + (f", {basics} basics" if basics else "")
                   + f"; {len(pkg.producers)} producers in every colour")
        out.append(f"    consumers: {', '.join(sorted(name[c] for c in cons))}")
        out.append(f"    producers: {', '.join(sorted(name[c] for c in spells)[:show])}"
                   + (" ..." if len(spells) > show else ""))
    for pkg, why in dropped:
        out.append(f"- dropped {label(pkg)} ({why}): "
                   f"{', '.join(sorted(name[c] for c in pkg.consumers))}")
    census: Counter = Counter()
    for c in supply.deckable:
        for n in walk(rec[c], skip=BackFace):
            if isinstance(n, TriggeredAbility):
                census[(type(n.event).__name__, bool(event_shape(n.event)))] += 1
    out.append("  triggers read: " + ", ".join(
        f"{k} {n}" for (k, ok), n in sorted(census.items()) if ok))
    out.append("  triggers skipped (the source's own, an opponent's, or a class not in the "
               "table): " + ", ".join(f"{k} {n}" for (k, ok), n in sorted(census.items())
                                       if not ok))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    from MTG_bot.core.executor.games import get_supply

    ap = argparse.ArgumentParser()
    ap.add_argument("sets", nargs="+")
    ap.add_argument("--pool", default="verified")
    a = ap.parse_args(argv)
    for set_code in a.sets:
        print(report(get_supply(a.pool, set_code), set_code))
    return 0


if __name__ == "__main__":
    sys.exit(main())
