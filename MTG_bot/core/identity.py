"""Identity primitives: what uniquely names a thing.

Two problems the legacy system had, and both are identity problems:

1. **The key was volatile.** Everything was keyed on ``cards.card_id``, an
   autoincrement rowid. The ingest drops and recreates the table, so a
   re-ingest renumbers every card and silently invalidates every learned
   embedding row. The fix (DESIGN_CARD_POOL.md, "Fix identity first"): key on
   ``scryfallOracleId`` — stable across re-ingests, semantic, the same id
   Scryfall uses. ``CardIdentity`` is frozen and keyed on that id.

2. **One integer axis for everything.** ``card_id`` and
   ``game_vocabulary.id`` shared one integer space and already collided. The
   fix: separate namespaces. A ``Handle`` carries its own ``namespace`` string,
   so a card's handle 5 and a zone's handle 5 are different values by
   construction. They cannot alias because the namespace is part of the
   identity, not an assumption.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Tuple

# Scryfall oracle ids are 36-char UUIDs. We validate shape, not value, so a
# malformed ingest (empty string, a rowid slipped in) is caught here rather
# than silently keying a card on something volatile.
_ORACLE_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def validate_oracle_id(oracle_id: str) -> str:
    """Return ``oracle_id`` if it is a well-formed scryfall oracle id, else raise."""
    if not isinstance(oracle_id, str) or not _ORACLE_ID_RE.match(oracle_id):
        raise ValueError(f"not a valid scryfall oracle id: {oracle_id!r}")
    return oracle_id


@dataclass(frozen=True, order=True)
class Handle:
    """A (namespace, index) identity for a live entity in a world.

    Two handles are equal only if *both* the namespace and the index match.
    That is the whole point of the namespace split: a card and a zone can both
    be "5" and never collide, because the namespace is part of the value.
    Handles are issued by a :class:`HandleSpace` and are stable for the life
    of the entity — no uuid4, no renumbering, deterministic and cheap to
    compare, hash, and serialise.
    """

    namespace: str
    index: int

    def __str__(self) -> str:
        return f"{self.namespace}:{self.index}"


class HandleSpace:
    """A monotonic integer allocator for one named namespace.

    ``allocate`` hands out 0, 1, 2, ... for that namespace and never reuses a
    number within a world. Different :class:`HandleSpace` instances are
    independent, which is what keeps the namespaces from sharing an axis.
    """

    __slots__ = ("name", "_next")

    def __init__(self, name: str) -> None:
        self.name = name
        self._next = 0

    def allocate(self) -> Handle:
        handle = Handle(self.name, self._next)
        self._next += 1
        return handle

    @property
    def count(self) -> int:
        return self._next


@dataclass(frozen=True)
class LegalityFlags:
    """Two independent flags, never one (DESIGN_CARD_POOL.md).

    ``format_legal``    — the banlist and set legality say the card may be played.
    ``engine_supported`` — every node in this card's ability tree has an executor
                           AND an encoder token.

    ``enabled`` is the "which cards are in the pool" notion: a card is playable
    only if it is legal *and* the engine can actually do what it says. A card
    that does not compile cleanly is not in the enabled pool — no silent
    degradation. ``engine_supported`` is also the coverage instrumentation:
    it is the number that tells us how much of a set the engine can run.
    """

    format_legal: bool = True
    engine_supported: bool = True

    @property
    def enabled(self) -> bool:
        return self.format_legal and self.engine_supported


@dataclass(frozen=True)
class CardIdentity:
    """The stable, oracle-id-keyed identity of a card.

    This is the *only* thing the engine and the network read about a card's
    printed characteristics. It is frozen and hashable so it can key the
    registry and the embedding tables. Volatile rowids never appear here.

    The fields are exactly the structured ingest that DESIGN_CARD_POOL.md
    step 1 calls for — the things the legacy ingest discarded: types,
    subtypes, colours, mana value, keywords, oracle id, and token-ness.
    """

    oracle_id: str
    name: str
    type_line: str = ""
    set_code: Optional[str] = None
    colors: Tuple[str, ...] = ()
    mana_cost: Optional[str] = None
    cmc: Optional[int] = None
    power: Optional[str] = None
    toughness: Optional[str] = None
    loyalty: Optional[str] = None
    keywords: Tuple[str, ...] = ()
    oracle_text: Optional[str] = None
    is_token: bool = False

    def __post_init__(self) -> None:
        validate_oracle_id(self.oracle_id)

    @property
    def primary_key(self) -> str:
        """The stable key everything else is keyed on: the oracle id."""
        return self.oracle_id

    def color_identity(self) -> FrozenSet[str]:
        """Set of colours in the card's mana cost and/or colour indicator."""
        cols = set(self.colors)
        if self.mana_cost:
            for c in "WUBRG":
                if c in self.mana_cost:
                    cols.add(c)
        return frozenset(cols)
