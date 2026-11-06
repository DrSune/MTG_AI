"""The deterministic canonical state model.

Every entity is named by an integer :class:`~MTG_bot.core.identity.Handle`
(stable, comparable, cheap) and every collection is *ordered*, so nothing here
iterates a set and nothing varies run to run under a fixed seed.
:meth:`GameWorld.fingerprint` is the canonical form: one deterministic hash of
the whole world, the question "is this the same position?" that loop detection
(docs/DESIGN_INFINITIES.md) and replay both ask.

Replay contract: two worlds built with the same seed and the same sequence of
moves have equal fingerprints at every step.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from MTG_bot.core.identity import CardIdentity, Handle, HandleSpace

# The zones a card can occupy. The stack is an ordered zone like the others.
ZONE_LIBRARY = "library"
ZONE_HAND = "hand"
ZONE_BATTLEFIELD = "battlefield"
ZONE_GRAVEYARD = "graveyard"
ZONE_EXILE = "exile"
ZONE_COMMAND = "command"
ZONE_STACK = "stack"

# Per-player zones. The stack is shared, so it is not in this list.
PLAYER_ZONES = (ZONE_LIBRARY, ZONE_HAND, ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_EXILE, ZONE_COMMAND)


@dataclass
class ZoneState:
    """One ordered zone. ``entries`` *is* the order: top of library is the
    last element, battlefield order is entry order. Deterministic."""

    handle: Handle
    kind: str
    controller: Handle  # the owning player's handle
    entries: List[Handle] = field(default_factory=list)

    def contains(self, card: Handle) -> bool:
        return card in self.entries


@dataclass
class CardState:
    """A card in the game: printed identity plus dynamic instance state.

    The split is deliberate (DESIGN_CARD_POOL.md): the *static* part is the
    :class:`CardIdentity` (what the card says) and the *dynamic* part
    (tapped, counters, ...) is a small per-instance vector that changes during
    the game. Keeping them separate is what makes the static card vector
    cacheable while play stays fast.
    """

    handle: Handle
    identity: CardIdentity
    tapped: bool = False
    counters: Dict[str, int] = field(default_factory=dict)  # e.g. "+1/+1": 2


@dataclass
class PlayerState:
    """One seat. ``seat`` is the anti-clockwise position, which is what
    trigger ordering sorts by (APNAP)."""

    handle: Handle
    seat: int
    name: str
    life: int
    mana_pool: Dict[str, int] = field(default_factory=dict)
    zones: Dict[str, ZoneState] = field(default_factory=dict)
    commander: Optional[Handle] = None

    def zone(self, kind: str) -> ZoneState:
        return self.zones[kind]


@dataclass
class TriggerInstance:
    """A triggered ability waiting to resolve.

    ``world.triggers`` holds them in queue order. The executor's drain
    (``TriggerBinder._pop_next``) resolves them as the stack would, the
    non-active player's simultaneous triggers first (CR 603.3b: the active
    player puts theirs on the stack first, and the stack resolves from the
    top).
    """

    source: Handle  # the card handle the trigger belongs to
    controller: Handle  # the player whose trigger it is
    controller_seat: int
    event: str
    clock: int


class GameWorld:
    """The canonical, deterministic game state.

    Every entity is addressed by an integer :class:`Handle` from its own
    namespace. Every zone is an ordered list. There is exactly one event clock,
    used for ordering only (never for identity). Build it, add seats and cards,
    move cards between zones, fire triggers — and the result of any sequence
    of moves is a function only of the seed and the moves. That is what makes
    the strength of a policy measurable at all.
    """

    def __init__(self, num_players: int = 2, start_life: int = 20, master_seed: int = 0) -> None:
        if num_players < 1:
            raise ValueError("need at least one player")
        self.master_seed = int(master_seed)

        # One namespace per entity kind. They cannot collide because the
        # namespace is part of the Handle's identity.
        self._players = HandleSpace("player")
        self._cards = HandleSpace("card")
        self._zones = HandleSpace("zone")

        self.players: Dict[Handle, PlayerState] = {}
        self.cards: Dict[Handle, CardState] = {}

        # seat order, anti-clockwise; player 0 is the active player at start
        self.player_order: List[Handle] = []
        self.active_player: Optional[Handle] = None
        self.turn: int = 1

        # single event clock, for trigger ordering only
        self._clock: int = 0
        self.triggers: List[TriggerInstance] = []

        for seat in range(num_players):
            self._add_player(seat, f"Player {seat + 1}", start_life)

    # ------------------------------------------------------------------ setup

    def _add_player(self, seat: int, name: str, life: int) -> Handle:
        handle = self._players.allocate()
        player = PlayerState(handle=handle, seat=seat, name=name, life=life)
        for kind in PLAYER_ZONES:
            zone_handle = self._zones.allocate()
            player.zones[kind] = ZoneState(handle=zone_handle, kind=kind, controller=handle)
        self.players[handle] = player
        self.player_order.append(handle)
        return handle

    # ------------------------------------------------------------------- adds

    def add_card(self, identity: CardIdentity, controller: Handle, zone: str = ZONE_LIBRARY) -> Handle:
        """Place a card in a zone. ``controller`` must be an existing player."""
        if controller not in self.players:
            raise KeyError(f"unknown player controller {controller}")
        if zone not in self.players[controller].zones:
            raise ValueError(f"player has no {zone!r} zone")
        handle = self._cards.allocate()
        self.cards[handle] = CardState(handle=handle, identity=identity)
        self.players[controller].zones[zone].entries.append(handle)
        return handle

    # ------------------------------------------------------------------- moves

    def zone_of(self, card: Handle) -> ZoneState:
        """The zone currently holding ``card``. Raises if the card is absent.

        Hot path: the full scan (every zone of every seat) dominated a self-play
        game's CPU. The zone last found for each card is remembered and
        RE-VALIDATED by membership before it is returned, so a move made by any
        code path (``move_card`` or a direct ``entries`` edit) can never make it
        answer wrong: a stale entry just falls through to the scan. Not part of
        the state: ``fingerprint`` does not read it and a deep copy carries it to
        the copied zones."""
        if card not in self.cards:
            raise KeyError(f"unknown card {card}")
        cache = self.__dict__.setdefault("_zone_cache", {})
        zone = cache.get(card)
        if zone is not None and card in zone.entries:
            return zone
        for player in self.player_order:
            for zone in self.players[player].zones.values():
                if zone.contains(card):
                    cache[card] = zone
                    return zone
        raise KeyError(f"card {card} is not in any zone")

    def controller_of(self, card: Handle) -> Handle:
        """The player who owns the zone ``card`` is in."""
        return self.zone_of(card).controller

    def move_card(self, card: Handle, target: ZoneState) -> None:
        """Move ``card`` to ``target``. Deterministic: it is removed from its
        old zone (by value, not by scan) and appended to the new one, so zone
        order is always entry order and there is no set difference."""
        source = self.zone_of(card)
        if source is target:
            return
        source.entries.remove(card)
        target.entries.append(card)

    def move_to_zone(self, card: Handle, controller: Handle, kind: str) -> None:
        self.move_card(card, self.players[controller].zone(kind))

    def draw(self, player: Handle, count: int = 1) -> List[Handle]:
        """Draw from the top of the library (last entry) into the hand."""
        lib = self.players[player].zone(ZONE_LIBRARY)
        hand = self.players[player].zone(ZONE_HAND)
        drawn: List[Handle] = []
        for _ in range(count):
            if not lib.entries:
                break
            card = lib.entries.pop()  # top of library
            hand.entries.append(card)
            drawn.append(card)
        return drawn

    # ---------------------------------------------------------------- triggers

    def tick(self) -> int:
        """Advance the event clock by one and return the new value."""
        self._clock += 1
        return self._clock

    def queue_trigger(self, source: Handle, controller: Handle, event: str) -> TriggerInstance:
        """Record a triggered ability, stamped with the next event clock."""
        trig = TriggerInstance(
            source=source,
            controller=controller,
            controller_seat=self.players[controller].seat,
            event=event,
            clock=self.tick(),
        )
        self.triggers.append(trig)
        return trig

    # --------------------------------------------------------------- canonical

    def _stable_str(self, card: Handle) -> str:
        c = self.cards[card]
        ident = c.identity
        counters = ",".join(f"{k}={v}" for k, v in sorted(c.counters.items()))
        return (
            f"{ident.oracle_id}|{ident.name}|tapped={int(c.tapped)}"
            f"|counters=[{counters}]"
        )

    def fingerprint(self) -> str:
        """A deterministic hash of the whole world.

        This is the canonical-form primitive: two worlds in the same position
        produce the same string. It is ordered by seat, then by zone order,
        then by zone-entry order, so it is a function only of the state — the
        basis for replay and loop detection (docs/DESIGN_INFINITIES.md).
        """
        h = hashlib.sha256()
        h.update(f"seed={self.master_seed}\n".encode())
        h.update(f"turn={self.turn} active={self.active_player}\n".encode())
        for player in self.player_order:
            p = self.players[player]
            h.update(f"seat={p.seat} life={p.life} mana={sorted(p.mana_pool.items())}\n".encode())
            for kind in PLAYER_ZONES:
                zone = p.zones[kind]
                h.update(f"{p.seat}:{kind}=[{','.join(str(e) for e in zone.entries)}]\n".encode())
            if p.commander is not None:
                h.update(f"{p.seat}:commander={p.commander}\n".encode())
        # card instance state (counters, tapped) is keyed by handle order
        for card in sorted(self.cards, key=lambda c: c.index):
            h.update(self._stable_str(card).encode())
        return h.hexdigest()
