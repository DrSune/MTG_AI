"""The deterministic canonical state model.

This is the state foundation for the D1 engine rebuild, and it exists to kill
the two defects that make the legacy state unmeasurable:

1. **Identity was uuid4.** ``game_graph.py`` minted a fresh UUID for every
   entity, and zone-change triggers were computed by iterating the *set
   difference* of those UUIDs. A set has no order, so under a fixed seed the
   trigger order still varied run to run. Integer handles (one
   :class:`~MTG_bot.core.identity.Handle` per namespace) are stable,
   comparable, and cheap, and every collection here is *ordered*, so there is
   no set difference anywhere to be nondeterministic.

2. **No canonical form.** Without a canonical serialisation you cannot ask
   "is this the same position as before?", which is the question loop
   detection (DESIGN_INFINITIES.md) and replay both need. :meth:`GameWorld.
   fingerprint` gives one deterministic hash of the whole world.

Replay contract: build two worlds with the same seed and the same sequence of
moves; their fingerprints must match at every step. That is the property the
tests pin down, and it is what P12 (byte-identical replay) will run on.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from MTG_bot.core.identity import CardIdentity, Handle, HandleSpace

# The zones a card can occupy. The stack is listed for completeness; its full
# APNAP/LIFO semantics are a Phase-2 concern. Phase 0 treats it as an ordered
# zone like the others so the state model is already total.
ZONE_LIBRARY = "library"
ZONE_HAND = "hand"
ZONE_BATTLEFIELD = "battlefield"
ZONE_GRAVEYARD = "graveyard"
ZONE_EXILE = "exile"
ZONE_COMMAND = "command"
ZONE_STACK = "stack"

ZONE_KINDS = frozenset(
    [ZONE_LIBRARY, ZONE_HAND, ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_EXILE, ZONE_COMMAND, ZONE_STACK]
)

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

    def __post_init__(self) -> None:
        if self.kind not in ZONE_KINDS:
            raise ValueError(f"unknown zone kind: {self.kind!r}")

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

    Ordering is the whole point. ``order_key`` is (controller seat, clock):
    seat first is APNAP (the active player acts first), clock second breaks
    ties among one player's own triggers in the order they were created. This
    is the deterministic replacement for the legacy set-difference trigger
    scan. Phase 2 replaces this queue with the real APNAP stack, keeping the
    same ordering invariant.
    """

    source: Handle  # the card handle the trigger belongs to
    controller: Handle  # the player whose trigger it is
    controller_seat: int
    event: str
    clock: int

    @property
    def order_key(self) -> tuple:
        return (self.controller_seat, self.clock)


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
        self.format: str = "standard"

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

    def add_player(self, name: str, life: int = 20) -> Handle:
        return self._add_player(len(self.player_order), name, life)

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
        """The zone currently holding ``card``. Raises if the card is absent."""
        if card not in self.cards:
            raise KeyError(f"unknown card {card}")
        for player in self.player_order:
            for zone in self.players[player].zones.values():
                if zone.contains(card):
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
        """Record a triggered ability. Ordered by (controller seat, clock)."""
        trig = TriggerInstance(
            source=source,
            controller=controller,
            controller_seat=self.players[controller].seat,
            event=event,
            clock=self.tick(),
        )
        self.triggers.append(trig)
        return trig

    def pending_triggers(self) -> List[TriggerInstance]:
        """Triggers in deterministic order (APNAP seat, then clock)."""
        return sorted(self.triggers, key=lambda t: t.order_key)

    def resolve_next_trigger(self) -> Optional[TriggerInstance]:
        """Pop and return the next trigger in deterministic order, else None."""
        if not self.triggers:
            return None
        self.triggers.sort(key=lambda t: t.order_key)
        return self.triggers.pop(0)

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
        basis for replay (P12) and loop detection (DESIGN_INFINITIES.md).
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

    def __len__(self) -> int:
        return len(self.cards)
