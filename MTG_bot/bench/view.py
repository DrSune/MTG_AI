"""The per-seat view: what one player may legally know (docs/DESIGN_BENCHMARK.md §3).

One projection for every agent, our bot and LLM seats alike. The review found every admitted
network omniscient (docs/REVIEW_2026-10-24.md A-1), and ``world_snapshot`` is an audit dump
that reveals hands by design (``core/executor/games.py:716``). This module is the play view.

Visibility, one rule (``_visible``):
- the viewer's own hand in full;
- every other hand and every library as a count only;
- battlefield, graveyards, exile, the command zone and the stack are public.

Object ids are opaque per-view labels (``o1``, ``o2``, …) assigned in the order objects first
become visible to this seat. They are never engine handles, which are allocated in deck order and
would leak library composition. Assigning them lazily from visible objects only is also what
makes the view byte-identical when hidden cards change (the metamorphic test in
``test_view.py``).

Live games carry no oracle text (``identity_of`` drops it, ``games.py:326-348``), so the text
comes from the same MTGJSON files the supply compiles (``OracleIndex``).

Known limit: cards a player has legitimately seen in a hidden zone (a revealed hand card, a
scried card that stayed on top) are not tracked, and show as hidden.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from MTG_bot.bench.masking import NameMasker
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_COMMAND,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
)

if TYPE_CHECKING:
    from MTG_bot.core.executor import Executor
    from MTG_bot.core.identity import Handle

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PUBLIC_ZONES = (ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_EXILE, ZONE_COMMAND)

#: Disclosed with every view: the engine is "batch Magic" (REVIEW A-3), and an agent should be
#: told the game it is playing.
ENGINE_NOTES = (
    "Engine notes: no priority passing; one action window per turn in the first main phase, "
    "then combat; opponents may respond only with counterspells and combat instants; "
    "mana pools do not empty between steps or turns."
)


class OracleIndex:
    """oracle_id -> printed oracle text, cost and type line, from ``MTG_bot/data/<SET>.json``."""

    _cache: ClassVar[dict[tuple[str, ...], OracleIndex]] = {}

    def __init__(self, set_codes: Iterable[str]) -> None:
        self.cards = {}
        for code in set_codes:
            self.cards.update(ingest_pool(DATA_DIR / f"{code}.json"))
        self.names = sorted({raw.identity.name for raw in self.cards.values()})
        self.token_names = sorted({raw.identity.name for raw in self.cards.values() if raw.is_token})

    @classmethod
    def for_sets(cls, *set_codes: str) -> OracleIndex:
        key = tuple(sorted(set_codes))
        if key not in cls._cache:
            cls._cache[key] = cls(key)
        return cls._cache[key]

    def text(self, oracle_id: str) -> str:
        raw = self.cards.get(oracle_id)
        return (raw.identity.oracle_text or "") if raw is not None else ""

    def cost(self, oracle_id: str) -> str | None:
        raw = self.cards.get(oracle_id)
        return raw.mana_cost_raw if raw is not None else None


@dataclass(frozen=True)
class ViewOptions:
    mask_names: bool = False
    salt: str = "public-dev"


@dataclass(frozen=True)
class CardView:
    oid: str
    name: str
    type_line: str
    cost: str | None
    text: str
    zone: str
    owner_seat: int
    controller_seat: int
    tapped: bool = False
    counters: tuple[tuple[str, int], ...] = ()
    power: int | None = None
    toughness: int | None = None
    keywords: tuple[str, ...] = ()
    damage: int = 0
    attached_to: str | None = None
    summoning_sick: bool = False
    printed_pt: str | None = None
    #: CR 702.26 (2026-10-29): a phased-out permanent is still on the table and public, but it is
    #: treated as though it does not exist; the engine's menus never offer it.
    phased_out: bool = False
    #: Ontology R5-1 (CR 610.3): this object was moved "until" an event and goes back when it
    #: happens: ``returns_to`` is the zone it returns to (its owner's), ``returns_when`` the event
    #: ("o3 leaves the battlefield", "end of turn", "seat 1's next turn"). None when it has no row.
    returns_to: str | None = None
    returns_when: str | None = None


@dataclass(frozen=True)
class PlayerView:
    seat: int
    is_viewer: bool
    life: int
    mana_pool: tuple[tuple[str, int], ...]
    hand_count: int
    library_count: int
    hand: tuple[CardView, ...] | None  # None: hidden from the viewer
    battlefield: tuple[CardView, ...]
    graveyard: tuple[CardView, ...]
    exile: tuple[CardView, ...]
    command: tuple[CardView, ...]


@dataclass(frozen=True)
class StackItemView:
    oid: str
    name: str
    controller_seat: int
    targets: tuple[str, ...]
    x_value: int | None
    kicked: bool


@dataclass(frozen=True)
class SeatView:
    viewer_seat: int
    turn: int
    active_seat: int
    players: tuple[PlayerView, ...]
    stack: tuple[StackItemView, ...]


def _visible(zone: str, owner_seat: int, viewer_seat: int) -> bool:
    if zone in PUBLIC_ZONES or zone == "stack":
        return True
    if zone == ZONE_HAND:
        return owner_seat == viewer_seat
    return False  # library: never, for anyone


class SeatLens:
    """The view of one seat across a whole game: stable opaque ids, optional masking."""

    def __init__(self, seat_index: int, oracle: OracleIndex, opts: ViewOptions | None = None):
        opts = opts or ViewOptions()
        self.seat_index = seat_index
        self.oracle = oracle
        self.opts = opts
        self.masker = NameMasker(oracle.names, opts.salt, keep=oracle.token_names) if opts.mask_names else None
        self._ids: dict[Handle, str] = {}
        self._handles: dict[str, Handle] = {}

    # ------------------------------------------------------------- identity

    def oid(self, handle: Handle) -> str:
        if handle not in self._ids:
            label = f"o{len(self._ids) + 1}"
            self._ids[handle] = label
            self._handles[label] = handle
        return self._ids[handle]

    def handle_of(self, oid: str) -> Handle | None:
        return self._handles.get(oid)

    def name(self, raw_name: str) -> str:
        return self.masker.label(raw_name) if self.masker else raw_name

    def text(self, raw_text: str) -> str:
        return self.masker.mask(raw_text) if self.masker else raw_text

    def seat_of(self, executor: Executor, player: Handle) -> int:
        return executor.world.player_order.index(player)

    def can_see(self, executor: Executor, handle: Handle) -> bool:
        world = executor.world
        if handle not in world.cards:
            return False
        zone = world.zone_of(handle)
        return _visible(zone.kind, self.seat_of(executor, zone.controller), self.seat_index)

    def describe(self, executor: Executor, handle: Handle, *, offered: bool = False) -> str:
        """A label for ``handle`` that names the card only if this seat may know it.

        ``offered``: the engine offered this object to this seat as a choice. The engine offers
        only objects the decider may choose among, and every choose-from-a-hidden-zone effect
        reveals or looks at the cards it offers, so an offered object may be named.
        """
        world = executor.world
        if handle in world.players:
            seat = self.seat_of(executor, handle)
            return f"seat {seat} ({'you' if seat == self.seat_index else 'opponent'})"
        if handle not in world.cards:
            return "an unknown object"
        if not (offered or self.can_see(executor, handle)):
            return "an unrevealed card"
        card = world.cards[handle]
        label = f"{self.oid(handle)} {self.name(card.identity.name)}"
        if world.zone_of(handle).kind == ZONE_BATTLEFIELD and card.identity.power is not None:
            p, t = executor.ledger.effective_pt(card.identity, handle, card.counters)
            label += f" ({p}/{t})"
        return label

    # ----------------------------------------------------------------- view

    def _card(self, executor: Executor, handle: Handle) -> CardView:
        world = executor.world
        card = world.cards[handle]
        ident = card.identity
        zone = world.zone_of(handle)
        owner_seat = self.seat_of(executor, zone.controller)
        on_bf = zone.kind == ZONE_BATTLEFIELD
        controller_seat = self.seat_of(executor, executor.controller_of(handle)) if on_bf else owner_seat
        power = toughness = None
        if ident.power is not None or ident.toughness is not None:
            if on_bf:
                power, toughness = executor.ledger.effective_pt(ident, handle, card.counters)
            else:
                power, toughness = _printed(ident.power), _printed(ident.toughness)
        keywords = tuple(sorted(executor.layers.keywords(handle))) if on_bf else tuple(sorted(ident.keywords))
        host = executor.attachments.get(handle) if on_bf else None
        returns_to, returns_when = self._returns(executor, handle)
        return CardView(
            oid=self.oid(handle),
            name=self.name(ident.name),
            type_line=self.text(ident.type_line),
            cost=self.oracle.cost(ident.oracle_id) or ident.mana_cost,
            text=self.text(self.oracle.text(ident.oracle_id) or (ident.oracle_text or "")),
            zone=zone.kind,
            owner_seat=owner_seat,
            controller_seat=controller_seat,
            tapped=bool(card.tapped) if on_bf else False,
            counters=tuple(sorted((k, v) for k, v in card.counters.items() if v)),
            power=power,
            toughness=toughness,
            keywords=keywords,
            damage=int(executor.damage.get(handle, 0)) if on_bf else 0,
            attached_to=self.oid(host) if host is not None else None,
            summoning_sick=_sick(executor, handle) if on_bf and "Creature" in ident.type_line else False,
            printed_pt=(
                f"{ident.power or '*'}/{ident.toughness or '*'}"
                if ident.power is not None or ident.toughness is not None
                else None
            ),
            phased_out=handle in executor.phased_out,
            returns_to=returns_to,
            returns_when=returns_when,
        )

    def _returns(self, executor: Executor, handle: Handle) -> tuple[str | None, str | None]:
        """Ontology R5-1 (CR 610.3): where and when an object moved "until" an event goes back,
        from the executor's return registry; (None, None) when it has no live row."""
        rows = [r for r in executor.returns.rows_for(handle) if executor.returns.still_there(executor, r)]
        if not rows:
            return None, None
        row = rows[-1]
        if row.tag == "UntilLeaves" and row.anchor is not None:
            when = f"{self.describe(executor, row.anchor)} leaves the battlefield"
        elif row.tag == "UntilNextTurn":
            when = f"seat {self.seat_of(executor, row.controller)}'s next turn begins"
        else:
            when = "end of turn"
        return row.previous_zone, when

    def view(self, executor: Executor) -> SeatView:
        world = executor.world
        players = []
        for seat, player_handle in enumerate(world.player_order):
            player = world.players[player_handle]
            zones = player.zones

            def cards(kind: str, zones: dict = zones) -> tuple[CardView, ...]:
                zone = zones.get(kind)
                if zone is None:
                    return ()
                return tuple(self._card(executor, h) for h in zone.entries)

            hand_zone = zones.get(ZONE_HAND)
            lib_zone = zones.get(ZONE_LIBRARY)
            players.append(
                PlayerView(
                    seat=seat,
                    is_viewer=seat == self.seat_index,
                    life=player.life,
                    mana_pool=tuple(sorted((c, n) for c, n in player.mana_pool.items() if n)),
                    hand_count=len(hand_zone.entries) if hand_zone else 0,
                    library_count=len(lib_zone.entries) if lib_zone else 0,
                    hand=cards(ZONE_HAND) if seat == self.seat_index else None,
                    battlefield=cards(ZONE_BATTLEFIELD),
                    graveyard=cards(ZONE_GRAVEYARD),
                    exile=cards(ZONE_EXILE),
                    command=cards(ZONE_COMMAND),
                )
            )
        stack = tuple(
            StackItemView(
                oid=self.oid(frame.handle),
                name=self.name(world.cards[frame.handle].identity.name),
                controller_seat=self.seat_of(executor, frame.controller),
                targets=tuple(self.describe(executor, t) for t in frame.declared_targets),
                x_value=frame.x_value,
                kicked=bool(frame.kicked),
            )
            for frame in reversed(executor.stack.frames)  # top first
        )
        active = world.active_player
        return SeatView(
            viewer_seat=self.seat_index,
            turn=world.turn,
            active_seat=self.seat_of(executor, active) if active is not None else -1,
            players=tuple(players),
            stack=stack,
        )


def _printed(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None  # '*' and friends: no printed number


def _sick(executor: Executor, handle: Handle) -> bool:
    from MTG_bot.core.executor.legality import _controlled_since_turn_start

    try:
        return not _controlled_since_turn_start(executor, handle)
    except Exception:  # noqa: BLE001 - a display flag must never crash a game
        return False


# ------------------------------------------------------------------- render


def _card_line(card: CardView) -> str:
    bits = [f"{card.oid} {card.name}"]
    if card.phased_out:
        bits.append("PHASED OUT (treated as though it does not exist)")
    if card.power is not None or card.toughness is not None:
        bits.append(f"{card.power}/{card.toughness}")
    if card.tapped:
        bits.append("tapped")
    if card.summoning_sick:
        bits.append("summoning-sick")
    if card.counters:
        bits.append("counters " + ",".join(f"{k}={v}" for k, v in card.counters))
    if card.damage:
        bits.append(f"damage {card.damage}")
    if card.attached_to:
        bits.append(f"attached to {card.attached_to}")
    if card.zone == ZONE_BATTLEFIELD and card.keywords:
        bits.append("keywords " + ",".join(k.lower() for k in card.keywords))
    if card.zone == ZONE_BATTLEFIELD and card.controller_seat != card.owner_seat:
        bits.append(f"controlled by seat {card.controller_seat}")
    if card.returns_to is not None:
        # R5-1 (CR 610.3): an object moved "until" an event, and where it goes back.
        bits.append(f"returns to its owner's {card.returns_to} when {card.returns_when}")
    return " ".join(bits)


def _zone_line(label: str, cards: tuple[CardView, ...]) -> str:
    return f"  {label}: " + ("; ".join(_card_line(c) for c in cards) if cards else "(none)")


def render_view(view: SeatView) -> str:
    """Canonical compact text: fixed order everywhere, one line per zone, then each distinct card
    text once. Stable byte-for-byte for the same view."""
    lines = [
        f"Turn {view.turn}. Seat {view.active_seat} is the active player. You are seat {view.viewer_seat}.",
        ENGINE_NOTES,
        "",
    ]
    texts: dict[str, CardView] = {}
    for p in view.players:
        pool = " ".join(f"{c}{n}" for c, n in p.mana_pool) or "(empty)"
        who = "you" if p.is_viewer else "opponent"
        head = f"Seat {p.seat} ({who}): life {p.life}"
        head += f", library {p.library_count} cards, mana pool {pool}"
        if p.hand is None:
            head += f", hand {p.hand_count} cards (hidden)"
        lines.append(head)
        if p.hand is not None:
            lines.append(_zone_line("hand", p.hand))
        for label, cards in (("battlefield", p.battlefield), ("graveyard", p.graveyard), ("exile", p.exile)):
            lines.append(_zone_line(label, cards))
        if p.command:
            lines.append(_zone_line("command zone", p.command))
        for card in (*(p.hand or ()), *p.battlefield, *p.graveyard, *p.exile, *p.command):
            texts.setdefault(card.name, card)
    if view.stack:
        lines.append("Stack (top first): " + "; ".join(
            f"{s.oid} {s.name} (seat {s.controller_seat})"
            + (f" targeting {', '.join(s.targets)}" if s.targets else "")
            + (f" X={s.x_value}" if s.x_value is not None else "")
            + (" kicked" if s.kicked else "")
            for s in view.stack
        ))
    else:
        lines.append("Stack: (empty)")
    lines.append("")
    lines.append("Card texts:")
    for name in sorted(texts):
        c = texts[name]
        parts = [name]
        if c.cost:
            parts.append(c.cost)
        parts.append(c.type_line)
        if c.printed_pt:
            parts.append(c.printed_pt)
        if c.text:
            parts.append(c.text.replace("\n", " / "))
        lines.append("  " + " | ".join(parts))
    return "\n".join(lines)
