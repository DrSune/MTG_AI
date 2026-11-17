"""Permissions to play cards from a zone: the engine side of ``Verb.PERMIT`` (DESIGN_ATOM_ONTOLOGY
§17, ontology round R13).

CR 601.3: a player may begin to cast a spell only if a rule or effect allows it. The rules allow a
spell in its owner's hand (CR 117.1a) and a land in it (CR 305.1). A PERMIT allows more, from one of
three places:

- a static ability of a permanent or an emblem: a "permit" layer record, live while the static
  functions (CR 604.2, 611.3a; ``layers._layer_live``). Conspicuous Snoop's Goblin spells from the
  top of the library, Omniscience's free casts from the hand;
- a static ability of the card itself, which functions from the zone it names (CR 113.6f), read
  off the card's record where it lies: Demonic Embrace's cast from the graveyard, flashback (CR
  702.34a);
- the effect of a resolving ability: a resolved "permit" record over the objects it named
  (``layers.register_permit``), lasting its duration (CR 611.2a) and losing an object that changes
  zones (CR 400.7). Chandra, Heart of Fire's "Until end of turn, you may play cards exiled this way".

A :class:`Path` is one way to play one card now. Timing is the card's own (CR 117.1a, 305.1): a
permission changes where a card may be played from and at what cost, never when.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from MTG_bot.core.ability_tree import (
    Atom,
    Cost,
    ReplacementAbility,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    Verb,
    ZoneKind,
    ZonePosition,
    _filter_names_the_source,
)
from MTG_bot.core.executor.quantity import eval_filter
from MTG_bot.core.executor.returns import moved_since
from MTG_bot.core.executor.selectors import ZONE_KIND_TO_STATE
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_EXILE, ZONE_GRAVEYARD, ZONE_HAND, ZONE_LIBRARY

if TYPE_CHECKING:  # pragma: no cover - typing only
    from MTG_bot.core.executor import Executor
    from MTG_bot.core.executor.layers import LayerRecord

#: The zones a card is played from through a permission (the IR's ``_permit_zones``).
PERMIT_ZONES = (ZONE_HAND, ZONE_GRAVEYARD, ZONE_EXILE, ZONE_LIBRARY)


@dataclass(frozen=True)
class Path:
    """One way to play ``card`` now: the PERMIT ``atom`` of ``source``. ``layer`` is its record
    (None: the card's own static, CR 113.6f, which counts no plays)."""

    card: Handle
    source: Handle
    atom: Atom
    layer: LayerRecord | None = None

    @property
    def lands(self) -> bool:
        return self.atom.args.get("lands") is True

    @property
    def alternative(self) -> Cost | None:
        value = self.atom.args.get("alternative")
        return value if isinstance(value, Cost) else None

    @property
    def additional(self) -> Cost | None:
        value = self.atom.args.get("additional")
        return value if isinstance(value, Cost) else None

    @property
    def rider(self) -> ReplacementAbility | None:
        value = self.atom.args.get("replace")
        return value if isinstance(value, ReplacementAbility) else None

    @property
    def key(self) -> tuple:
        """What a cast through this path pays and what becomes of the spell (R5-2 v3 point 6:
        an option is the object and its cost path; permissions sharing one give one option)."""
        return (self.alternative, self.additional, self.rider)

    @property
    def plain(self) -> bool:
        """The card's own cost and nothing after: the hand's path, from another zone."""
        return self.key == (None, None, None)

    @property
    def counted(self) -> bool:
        return self.layer is not None and self.layer.uses is not None


def _zone_state(executor: Executor, seat: Handle, card: Handle) -> str | None:
    """The zone of ``card`` among ``seat``'s own that a permission can name, or None: a library
    card only on top (the zones' TOP position is the only library one the IR takes)."""
    world = executor.world
    zone = world.zone_of(card)
    if zone.controller != seat or zone.kind not in PERMIT_ZONES:
        return None
    if zone.kind == ZONE_LIBRARY and (not zone.entries or zone.entries[-1] != card):
        return None
    return zone.kind


def _names(sel: Selector, state: str) -> bool:
    """Does ``sel`` name the zone a card in ``state`` lies in (its own controller's, the top of
    the library)?"""
    for zone in sel.zones:
        if ZONE_KIND_TO_STATE.get(zone.kind) != state:
            continue
        if zone.kind is ZoneKind.LIBRARY and zone.position is not ZonePosition.TOP:
            continue
        return True
    return False


def _population(atom: Atom) -> bool:
    """Does the PERMIT name a population (every card of its zone that passes the filter, read
    whenever a card is played) rather than objects designated as it resolved?"""
    sel = atom.args.get("source")
    return isinstance(sel, Selector) and sel.referent is None and sel.mode is SelectorMode.ALL


def _covers(executor: Executor, seat: Handle, source: Handle, atom: Atom, card: Handle,
            state: str) -> bool:
    """Does a static PERMIT of ``source`` cover ``card`` in ``state`` now: its zone named, its
    filter passed in the permission's coordinates (its source, its controller ``seat``)?"""
    sel = atom.args.get("source")
    if not isinstance(sel, Selector) or not _names(sel, state):
        return False
    from MTG_bot.core.executor.legality import ctx_for

    return eval_filter(sel.filter, card, ctx_for(executor, source, seat))


def own_permits(record: object) -> list[tuple[StaticAbility, Atom]]:
    """The PERMITs of a card's own statics about the card itself ("You may cast this card from
    your graveyard", flashback): they function from the zone they name (CR 113.6f)."""
    out: list[tuple[StaticAbility, Atom]] = []
    for ability in getattr(record, "abilities", ()):
        if not isinstance(ability, StaticAbility):
            continue
        effect = ability.effect
        for atom in effect.steps if isinstance(effect, Seq) else (effect,):
            sel = atom.args.get("source") if isinstance(atom, Atom) else None
            if (
                isinstance(atom, Atom)
                and atom.verb is Verb.PERMIT
                and isinstance(sel, Selector)
                and _filter_names_the_source(sel.filter)
            ):
                out.append((ability, atom))
    return out


def paths(executor: Executor, seat: Handle, card: Handle) -> list[Path]:
    """Every way ``seat`` may cast ``card`` now through a permission, one per cost path
    (:attr:`Path.key`): an uncounted permission before a counted one, then the oldest. A land's
    play is :func:`land_path`'s (a cast permission sharing a cost path never stands for it)."""
    best: dict[tuple, Path] = {}
    for path in _found(executor, seat, card):
        held = best.get(path.key)
        if held is None or _better(path, held):
            best[path.key] = path
    return sorted(best.values(), key=_order)


def _found(executor: Executor, seat: Handle, card: Handle) -> list[Path]:
    """Every permission that lets ``seat`` play ``card`` now, before :func:`paths` keeps one per
    cost path."""
    from MTG_bot.core.executor.legality import ctx_for, spell_record

    state = _zone_state(executor, seat, card)
    if state is None:
        return []
    found: list[Path] = []
    for layer in executor.layers.records:
        if layer.kind != "permit" or layer.status != "live" or layer.controller != seat:
            continue
        atom = layer.payload[0]
        if layer.uses == 0:
            continue
        if layer.resolved and not _population(atom):
            # a designation: the objects named as it resolved, each while it stays (CR 400.7)
            if (
                card not in layer.targets
                or state == ZONE_LIBRARY
                or moved_since(executor.journal, card, layer.since)
            ):
                continue
        elif not _covers(executor, seat, layer.source, atom, card, state):
            # a population, a static's or a resolving one's (a rules change, CR 611.2c): read now
            continue
        found.append(Path(card, layer.source, atom, layer))
    record = spell_record(executor, card)
    for static, atom in own_permits(record):
        if not _covers(executor, seat, card, atom, card, state):
            continue
        if static.condition is not None and not eval_filter(
            static.condition, card, ctx_for(executor, card, seat)
        ):
            continue
        found.append(Path(card, card, atom, None))
    if state == ZONE_HAND:  # the rules' own path is the plain one (CR 117.1a)
        found = [p for p in found if p.alternative is not None]
    return found


def _better(a: Path, b: Path) -> bool:
    """Of two permissions offering one cost path, use the one that costs no counted play, then
    the older (a dominant rule, not a strategy: the other one's play stays)."""
    if a.counted != b.counted:
        return not a.counted
    return _seq(a) < _seq(b)


def _seq(path: Path) -> int:
    return path.layer.seq if path.layer is not None else 0


def _order(path: Path) -> tuple:
    return (not path.plain, str(path.source), _seq(path))


def land_path(executor: Executor, seat: Handle, card: Handle) -> Path | None:
    """The permission ``seat`` plays the land ``card`` with from outside its hand (CR 305.1,
    116.2a), or None. A land play has no cost, so any one serves: an uncounted one first."""
    if executor.world.zone_of(card).kind == ZONE_HAND:
        return None
    lands = [p for p in _found(executor, seat, card) if p.lands]
    if not lands:
        return None
    return min(lands, key=lambda p: (p.counted, _seq(p)))


def cast_paths(executor: Executor, seat: Handle, card: Handle) -> list[Path]:
    """The permissions ``seat`` may cast ``card`` through now, one per cost path (a land is
    never cast, CR 305.9: the caller asks ``stack.is_land_card`` first)."""
    return paths(executor, seat, card)


def playable(executor: Executor, seat: Handle) -> list[Handle]:
    """The cards ``seat`` may play through a permission now, in a fixed order: the graveyard,
    exile, the top of the library, then the hand (its cost-changing paths)."""
    world = executor.world
    player = world.players[seat]
    out: list[Handle] = []
    for state in (ZONE_GRAVEYARD, ZONE_EXILE, ZONE_LIBRARY, ZONE_HAND):
        zone = player.zones.get(state)
        if zone is None or not zone.entries:
            continue
        cards = [zone.entries[-1]] if state == ZONE_LIBRARY else list(zone.entries)
        out.extend(c for c in cards if _found(executor, seat, c))
    return out


def use(path: Path) -> None:
    """A play made through ``path`` uses one of its plays (Idol of Endurance's "a creature
    spell"); a permission with none left ends."""
    layer = path.layer
    if layer is None or layer.uses is None:
        return
    layer.uses -= 1
    if layer.uses <= 0:
        layer.status = "expired"
