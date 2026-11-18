"""The tree shapes of the open engine faults (KNOWLEDGE/2026-11-18/215 §4), for the latent-fault
guard (``tools/audit/test_fault_reachability.py``).

A fault reaches a game only through a card that holds its shape, and a training game deals one set
(``games.get_supply("verified", code)``). Each shape here is a function from one pool's cards to the
names of the cards holding it, named by 215's fault id. They are ``census.py``'s detectors
(``reports/engine_fault_triage_2026-11-18/``), kept where 215 judged them to encode a fault's
shape, and narrowed where its census listed a broader carrier set (F18d, F38, F40): a shape that
names a card should mean the card can reach the fault, or be one of the carriers 215 judged. A
fault a wave closes loses its shape here (wave W1: F14, F14b, F33, F44, F45d, F48, F50; F14c's
shape stays for its residue).

What a shape cannot see (215 §3): wordings no tree shows (the text census), and a fault whose reach
needs two cards in one game (F27's self-damage and lifelink) is the pair of its halves' sets.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator
from typing import Any

from MTG_bot.core import ability_tree as at

#: Ability node kinds: the innermost one holding a node names where it acts.
ABILITY_KINDS = ("TriggeredAbility", "ActivatedAbility", "StaticAbility", "SpellAbility",
                 "ReplacementAbility", "EtBState", "DelayedTrigger", "KeywordAbility")


def walk(node: Any, path: tuple = ()) -> Iterator[tuple[tuple, Any]]:
    """(path, node) for every dataclass node; the path is a tuple of (class name, field) pairs, an
    AtomArgs role as ("role", name)."""
    yield path, node
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        for f in dataclasses.fields(node):
            yield from _value(getattr(node, f.name), (*path, (type(node).__name__, f.name)))


def _value(v: Any, path: tuple) -> Iterator[tuple[tuple, Any]]:
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        yield from walk(v, path)
    elif isinstance(v, (tuple, frozenset, list)):
        for item in v:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str):
                yield from _value(item[1], (*path, ("role", item[0])))  # an AtomArgs pair
            else:
                yield from _value(item, path)


def outer(path: tuple) -> str:
    """The innermost ability kind holding the node (a granted ability inside an effect counts)."""
    return next((c for c, _f in reversed(path) if c in ABILITY_KINDS or c in ("TokenSpec", "EmblemSpec")), "?")


def zones_of(sel: Any) -> set:
    return {z.kind for z in sel.zones} if isinstance(sel, at.Selector) else set()


def atoms(card: Any, *verbs: at.Verb) -> Iterator[tuple[tuple, at.Atom]]:
    for path, n in walk(card):
        if isinstance(n, at.Atom) and (not verbs or n.verb in verbs):
            yield path, n


Shape = Callable[[list], set]


def each(holds: Callable[[Any], bool]) -> Shape:
    """A shape one card holds alone."""
    return lambda cards: {c.name for c in cards if holds(c)}


# ---------------------------------------------------------------- the reachable faults' carriers

def f13_carrier(card: Any) -> bool:
    """A static restriction on the card's own targeting ("can target only a tapped creature"), a
    PREVENT_EFFECT over a TargetingEvent: read again at resolution today (CR 601.2c, 608.2b)."""
    return any(outer(p) == "StaticAbility" and isinstance(a.args.get("event"), at.TargetingEvent)
               for p, a in atoms(card, at.Verb.PREVENT_EFFECT))


def multi_slot_trigger(card: Any, with_choose: bool | None = None) -> bool:
    """A triggered ability with two or more target slots (F18b: its asks look alike); with
    ``with_choose``, one that also holds a Choose (F18d: it raises)."""
    for _p, n in walk(card):
        if isinstance(n, (at.TriggeredAbility, at.DelayedTrigger)):
            slots = {repr(s) for _q, s in walk(n.effect) if isinstance(s, at.Selector) and s.mode is at.SelectorMode.TARGET}
            choose = any(isinstance(x, at.Choose) for _q, x in walk(n.effect))
            if len(slots) > 1 and (with_choose is None or choose == with_choose):
                return True
    return False


def f19_carrier(card: Any) -> bool:
    """Gives a player an ability (hexproof, protection): no observation shows a player's keywords."""
    return any(isinstance(sel := a.args.get("target"), at.Selector) and at.ZoneKind.PLAYER in zones_of(sel)
               for _p, a in atoms(card, at.Verb.GRANT_ABILITY))


def f27_self_damage(card: Any) -> bool:
    """DEAL_DAMAGE whose recipients can include its controller ("each player", "you", "any target")."""
    for _p, a in atoms(card, at.Verb.DEAL_DAMAGE):
        t = a.args.get("target")
        if isinstance(t, at.Selector) and at.ZoneKind.PLAYER in zones_of(t):
            refs = {z.controller.name for z in t.zones if z.kind is at.ZoneKind.PLAYER}
            if refs & {"ANY", "YOU", "EACH"} or t.mode is at.SelectorMode.ALL:
                return True
    return False


def f27_lifelink(card: Any) -> bool:
    """Has or gives lifelink: a printed keyword, a grant, a token's keyword (an enum leaf the node
    walk does not yield, so the tree's text is read)."""
    return f"Keyword.{at.Keyword.LIFELINK.name}" in repr(card)


def f43_carrier(card: Any) -> bool:
    """A "you may" whose action needs an object (a sacrifice, a discard, a payment, a choice): it is
    offered when it can do nothing (CR 609.3; a phantom decision)."""
    return any(isinstance(n, at.OptionalEffect)
               and {a.verb.name for _q, a in walk(n.inner) if isinstance(a, at.Atom)}
               & {"SACRIFICE", "MOVE_ZONE", "PAY", "DISCARD", "CHOOSE"}
               for _p, n in walk(card))


# --------------------------------------------- the latent faults (no card should hold the shape)

def f14c_carrier(card: Any) -> bool:
    """An effect that exiles an object and returns it in the same resolution (a flicker). Its last
    known information survives since E1 (85dd1bfa; W1 pins it), but an Aura flickered so loses the
    attachment it returns with: the binder detaches the old object at the next drain, after the
    return attached the new one (BACKLOG, "What engine wave W1 left")."""
    for _p, n in walk(card):
        if isinstance(n, at.Seq):
            exiled = False
            for step in n.steps:
                for _q, a in walk(step):
                    if not (isinstance(a, at.Atom) and a.verb is at.Verb.MOVE_ZONE):
                        continue
                    dest = a.args.get("destination")
                    sel = a.args.get("cards") or a.args.get("target")
                    kind = dest.kind if isinstance(dest, at.Zone) else None
                    if exiled and kind is at.ZoneKind.BATTLEFIELD and getattr(sel, "referent", None) is not None:
                        return True
                    exiled = exiled or kind is at.ZoneKind.EXILE
    return False


def f38_carrier(card: Any) -> bool:
    """An "as this enters" effect other than a choice of name (only CHOOSE_NAME runs; any other raises)."""
    return any(isinstance(n, at.EtBState) and n.effect is not None
               and {a.verb for _q, a in walk(n.effect) if isinstance(a, at.Atom)} - {at.Verb.CHOOSE_NAME}
               for _p, n in walk(card))


def chooses_as_it_enters(card: Any) -> bool:
    return any(isinstance(n, at.EtBState) and n.effect is not None
               and any(isinstance(a, at.Atom) and a.verb is at.Verb.CHOOSE_NAME for _q, a in walk(n.effect))
               for _p, n in walk(card))


def copies(card: Any) -> bool:
    """A copy effect: a COPY atom, or a token or object made "a copy of" another (CopyOf, CR 707).
    No pool card has one yet; the copy round (209 B3) brings them, with F29, F40 and F60."""
    return any(isinstance(n, at.CopyOf) or isinstance(n, at.Atom) and n.verb is at.Verb.COPY
               for _p, n in walk(card))


def f29_shape(cards: list) -> set:
    """Two token specs of one name with different bytes and abilities in one pool: the binder keys a
    token's record by its name, so one reads the other's abilities (CR 111.3, 707.9)."""
    specs: dict[str, set[str]] = {}
    owners: dict[str, set[str]] = {}
    for card in cards:
        for _p, n in walk(card):
            if isinstance(n, at.TokenSpec) and n.abilities:
                specs.setdefault(n.name, set()).add(repr(n))
                owners.setdefault(n.name, set()).add(card.name)
    return {name for token, made in specs.items() if len(made) > 1 for name in owners[token]}


def f40_shape(cards: list) -> set:
    """A copy effect beside a card that chooses as it enters: a copy that entered without choosing
    raises (CR 707.2; Icon of Ancestry's ruling). Empty while no pool card copies."""
    if not any(copies(c) for c in cards):
        return set()
    return {c.name for c in cards if chooses_as_it_enters(c) or copies(c)}


def f04(card: Any) -> bool:
    """Verb.DISCARD, which has no executor handler (I8's fold)."""
    return any(True for _p, _a in atoms(card, at.Verb.DISCARD))


def f10d(card: Any) -> bool:
    """A damage trigger naming a dealer and no recipient: a split blow (trample, two blockers)
    fires it once per row (CR 603.2c)."""
    return any(isinstance(n, (at.TriggeredAbility, at.DelayedTrigger)) and isinstance(n.event, at.DamageDealtEvent)
               and n.event.source is not None and isinstance(n.event.filter, at.FAnd) and not n.event.filter.children
               for _p, n in walk(card))


def f11(card: Any) -> bool:
    """A creature that can block more than one attacker (CR 509.1, 510.1d; one block each today)."""
    return any(isinstance(n, at.KeywordAbility) and "BLOCK" in n.keyword.name
               or isinstance(n, at.FAtom) and "BLOCK_ADDITIONAL" in n.pred.name for _p, n in walk(card))


def f17(card: Any) -> bool:
    """An activated ability with X in its cost and a target: it takes the targets before X (CR 601.2b)."""
    return any(isinstance(ab, at.ActivatedAbility)
               and any(isinstance(n, at.QX) for _p, n in walk(ab.cost))
               and any(isinstance(n, at.Selector) and n.mode is at.SelectorMode.TARGET for _p, n in walk(ab.effect))
               for ab in card.abilities)


def f46(card: Any) -> bool:
    """MOVE_ZONE's top-n draw idiom into a hand (an unpartitioned, referent-free, unfiltered
    selector over one library: ``verbs._v_move_zone``'s draw lane, ``gates._draw_idiom``'s test)
    that is not "your library into your hand": the lane takes the cards from the library of the
    destination's player (``zone_owner``, the ability's controller for OWNER or ANY), not from the
    selector's library, and puts them in that player's hand (CR 108.3, 400.3: the selector's
    library, its owner's hand). The mill lane (``pop_order``) names its library itself and is right."""
    you = at.ControllerRef
    for _p, a in atoms(card, at.Verb.MOVE_ZONE):
        sel, dest = a.args.get("cards"), a.args.get("destination")
        if not (isinstance(sel, at.Selector) and isinstance(dest, at.Zone) and dest.kind is at.ZoneKind.HAND):
            continue
        partition = sel.mode in (at.SelectorMode.ONE_OF, at.SelectorMode.REST) or (
            sel.mode is at.SelectorMode.ALL
            and any(z.kind is at.ZoneKind.LIBRARY and z.position is at.ZonePosition.TOP for z in sel.zones))
        draw = (not partition and sel.referent is None and len(sel.zones) == 1
                and sel.zones[0].kind is at.ZoneKind.LIBRARY and isinstance(sel.filter, at.FAnd)
                and not sel.filter.children)
        if draw and (sel.zones[0].controller is not you.YOU
                     or dest.controller not in (you.YOU, you.OWNER, you.ANY)):
            return True
    return False


def f53(card: Any) -> bool:
    """A zone-change replacement on its own source from ANY zone ("from anywhere"): it works on the
    battlefield only (CR 614.1, 113.6)."""
    return any(isinstance(n, at.ReplacementAbility) and isinstance(n.event, at.ZoneChangeEvent)
               and n.event.from_zone.kind is at.ZoneKind.ANY and isinstance(n.event.subject, at.FAtom)
               and n.event.subject.pred is at.FAtomPred.IS_SOURCE for _p, n in walk(card))


def f56(card: Any) -> bool:
    """A hybrid mana cost (CR 107.4e)."""
    return any(isinstance(n, at.CostManaHybrid) for _p, n in walk(card))


def f57(card: Any) -> bool:
    """A singular OPPONENT/ALL_OPPONENTS/ANY player ref on a one-player verb: it raises at three or
    more seats (B-108)."""
    one = {at.Verb.DRAW, at.Verb.SCRY, at.Verb.LOOK_AT, at.Verb.REVEAL, at.Verb.ADD_MANA, at.Verb.GAIN_CONTROL}
    refs = (at.ControllerRef.OPPONENT, at.ControllerRef.ALL_OPPONENTS, at.ControllerRef.ANY)
    return any(isinstance(c := a.args.get("controller"), at.ControllerRef) and c in refs
               for _p, a in atoms(card, *one))


def f61(card: Any) -> bool:
    """A Saga (lore counters, CR 714) or a postcombat-main trigger: neither is modelled."""
    return "Saga" in card.subtypes


# --------------------------------------- latent: the carriers 215 judged unable to reach the fault

def f31_carrier(card: Any) -> bool:
    """A reader of "exiled with ~" (IS_EXILED_WITH_SOURCE): three moments of it are wrong (CR 607.2a)."""
    return any(isinstance(n, at.FAtom) and n.pred.name == "IS_EXILED_WITH_SOURCE" for _p, n in walk(card))


def f35_life(cards: list) -> set:
    """Two different life-gain replacements in one pool: their order is never asked (CR 616.1)."""
    have = {c.name for c in cards if any(isinstance(n, at.ReplacementAbility) and isinstance(n.event, at.LifeGainedEvent)
                                         for _p, n in walk(c))}
    return have if len(have) > 1 else set()


def f36_carrier(card: Any) -> bool:
    """An ALL selector over a library's top (the look window written on every read)."""
    return any(isinstance(n, at.Selector) and n.mode is at.SelectorMode.ALL
               and any(z.kind is at.ZoneKind.LIBRARY and z.position is at.ZonePosition.TOP for z in n.zones)
               for _p, n in walk(card))


def f37_carrier(card: Any) -> bool:
    """A CHOOSE of "any number" (QUnbounded): over a menu no ask can show, it takes all (CR 107.1c)."""
    return any(isinstance(n, at.Selector) and n.mode is at.SelectorMode.CHOOSE and isinstance(n.count, at.QUnbounded)
               and n.referent is None for _p, n in walk(card))


def f41_carrier(card: Any) -> bool:
    """A move into a library that is not its controller's ("picks from another player's library or
    hand raise")."""
    return any(isinstance(d := a.args.get("destination"), at.Zone) and d.kind is at.ZoneKind.LIBRARY
               and d.controller is not at.ControllerRef.YOU for _p, a in atoms(card, at.Verb.MOVE_ZONE))


def f47_carrier(card: Any) -> bool:
    """A Conditional after a step that made two or more tokens (it judges one of them)."""
    for _p, n in walk(card):
        if isinstance(n, at.Seq):
            many = False
            for step in n.steps:
                if isinstance(step, at.Atom) and step.verb is at.Verb.CREATE_TOKEN:
                    c = step.args.get("count")
                    many = not (c is None or isinstance(c, at.QConst) and c.value == 1)
                elif isinstance(step, at.Conditional) and many:
                    return True
    return False
