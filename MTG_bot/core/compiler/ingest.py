"""Structured ingest of MTGJSON v5 pool files (compiler step 1).

Turns an MTGJSON v5 dump into structured per-card records before any template matching, so
nothing downstream reads an English string for meaning. It keeps only what is structured:

- ``CardIdentity`` (core/identity.py), keyed on ``identifiers.scryfallOracleId``. The oracle id is
  the primary key everywhere; card numbers and per-printing uuids never become keys or fields.
- Printed characteristics as structured fields: type line, types, subtypes, supertypes, colours,
  colour identity, the mana cost string, the mana value as an int, P/T and loyalty as the printed
  strings, keywords.
- The oracle text split into a deterministic sentence tuple (``sentences``, see
  ``split_sentences``): the template compiler's input.

Deliberate non-goals:

- No NLP. ``token_name_refs`` is ``()`` by construction: token names are bare subtype words
  ("Angel", "Knight"), so a bare occurrence in the text is no token-creation signal ("is a Knight
  in addition to its other types" creates no token). Matching the whole "create a ... token"
  sentence belongs to the template compiler.
- ``UnknownCardError`` is not raised here: ingest stores no cross-card references. Malformed data
  that a clean MTGJSON file never holds is ``StateCorruptionError``.

Reprint duplicates: a pool file can repeat a card, every captured field identical and only raw
fields the ingest drops (card number, uuid, rarity) differing. The oracle id names the card, not
the printing, so ``ingest_pool`` keeps the first of identical duplicates ("identical" per
:func:`_dedup_key`) and raises ``StateCorruptionError`` only when one oracle id maps to two
different records.

Modal-DFC face fold: MTGJSON stores each face of a ``modal_dfc`` card as its own record with
``side`` ``"a"`` / ``"b"``, sharing the oracle id. After the per-side reprint dedup, ``ingest_pool``
folds exactly that pattern: the side-``"a"`` record becomes the ``RawCard`` and the side-``"b"``
record its structured ``back_face``. Every other duplicate-oracle-id mismatch still raises.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from MTG_bot.core.errors import StateCorruptionError
from MTG_bot.core.identity import CardIdentity, validate_oracle_id

_SENTENCE_END_CHARS = frozenset(".?!")
_WHITESPACE = frozenset(" \t\r\n")


def split_sentences(text: str | None) -> tuple[str, ...]:
    """Split oracle text into a deterministic sentence tuple (no NLP).

    A sentence ends at a line break (any paren depth) or at ``[.?!]`` followed by whitespace at
    paren depth 0, so a multi-sentence parenthetical reminder ("Opt (Look at the top card of your
    library. You may put that card on the bottom.)") stays one sentence. Chunks are stripped and
    empties dropped; ``None`` or blank text gives ``()``. A stray ``)`` never takes the depth below
    zero.
    """
    if not text:
        return ()
    sentences: list[str] = []
    current: list[str] = []
    depth = 0
    length = len(text)

    def flush() -> None:
        chunk = "".join(current).strip()
        if chunk:
            sentences.append(chunk)
        current.clear()

    i = 0
    while i < length:
        char = text[i]
        if char == "\n":
            flush()
            i += 1
            continue
        if char == "(":
            depth += 1
            current.append(char)
            i += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            current.append(char)
            i += 1
            continue
        if depth == 0 and char in _SENTENCE_END_CHARS:
            # A boundary needs at least one whitespace char after the punctuation.
            j = i + 1
            while j < length and text[j] in _WHITESPACE:
                j += 1
            if j > i + 1:
                current.append(char)
                flush()
                i = j
                continue
        current.append(char)
        i += 1
    flush()
    return tuple(sentences)


@dataclass(frozen=True)
class CardFace:
    """Structured data of one face of a modal double-faced card.

    Carries exactly the printed-characteristic fields :class:`RawCard`
    captures (same field pipeline, same :func:`split_sentences`), minus the
    identity and pool-level flags: a face shares its card's oracle id and
    layout, and is never a token or emblem in its own right. ``name`` is
    the record's ``faceName``, or the half of the combined ``"A // B"``
    name that follows the separator when ``faceName`` is absent.
    """

    name: str
    type_line: str
    types: tuple[str, ...]
    subtypes: tuple[str, ...]
    supertypes: tuple[str, ...]
    colors: tuple[str, ...]
    color_identity: frozenset[str]
    mana_cost_raw: str | None
    mana_value: int
    power_raw: str | None
    toughness_raw: str | None
    loyalty_raw: str | None
    keywords: tuple[str, ...]
    sentences: tuple[str, ...]


# MTGJSON combined name separator for double-faced records.
_FACE_NAME_SPLIT = " // "


@dataclass(frozen=True)
class RawCard:
    """A structured per-card record: the compiler's ingest unit.

    Every field is structured; the only English that survives is the *data*
    itself (name, type line, keyword strings, the sentence tuple), never a
    semantic annotation. ``sentences`` is what the template compiler
    matches against; ``identity.oracle_id`` is what everything else is
    keyed on. ``back_face`` is ``None`` for every single-faced card and the
    structured back face for a modal DFC folded by :func:`ingest_pool`.
    """

    identity: CardIdentity
    type_line: str
    types: tuple[str, ...]
    subtypes: tuple[str, ...]
    supertypes: tuple[str, ...]
    colors: tuple[str, ...]
    color_identity: frozenset[str]
    mana_cost_raw: str | None
    mana_value: int
    power_raw: str | None
    toughness_raw: str | None
    loyalty_raw: str | None
    keywords: tuple[str, ...]
    sentences: tuple[str, ...]
    layout: str
    is_token: bool
    is_emblem: bool
    token_name_refs: tuple[str, ...]
    related_names: tuple[str, ...]
    back_face: CardFace | None = None


def _as_str(raw: dict[str, Any], key: str, card: str) -> str | None:
    """Read an optional string field (None when absent or null); raise on a wrong type."""
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise StateCorruptionError(
            f"card {card!r}: field {key!r} is not a string",
            context={"card": card, "field": key, "got": type(value).__name__},
        )
    return value


def _as_str_tuple(raw: dict[str, Any], key: str, card: str) -> tuple[str, ...]:
    """Read a list-of-strings field (``()`` when absent or null)."""
    value = raw.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise StateCorruptionError(
            f"card {card!r}: field {key!r} is not a list of strings",
            context={"card": card, "field": key, "got": type(value).__name__},
        )
    return tuple(value)


def _related_names(raw: dict[str, Any], card: str) -> tuple[str, ...]:
    """The related-card names a record links to, sorted and deduped.

    ``relatedCards`` is an MTGJSON object mapping relationship keys
    (``reverseRelated``, ``tokens``, …) to lists of related-card
    identifiers. The canonical v5 contract says these lists are card
    *names*; the M21 dump instead fills ``tokens`` with record *uuids*
    while ``reverseRelated`` carries names. Either way the linkage is
    structured (no NLP), so :class:`RawCard` keeps the raw union verbatim.
    An emblem's only key is ``reverseRelated``, so its union is its owner's
    name: the emblem -> owner association.
    """
    value = raw.get("relatedCards")
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise StateCorruptionError(
            f"card {card!r}: field 'relatedCards' is not an object",
            context={"card": card, "got": type(value).__name__},
        )
    names: set[str] = set()
    for key, entries in value.items():
        if entries is None:
            continue
        if not isinstance(entries, list) or not all(
            isinstance(x, str) for x in entries
        ):
            raise StateCorruptionError(
                f"card {card!r}: relatedCards[{key!r}] is not a list of strings",
                context={"card": card, "key": key, "got": type(entries).__name__},
            )
        names.update(entries)
    return tuple(sorted(names))


def _mana_value(raw: dict[str, Any], card: str) -> int:
    """The mana value as an int: ``manaValue`` if present, else 0.

    Lands, tokens and other no-cost cards carry no ``manaValue``: they are
    0, never ``None``.
    """
    value = raw.get("manaValue")
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StateCorruptionError(
            f"card {card!r}: manaValue is not a number",
            context={"card": card, "got": type(value).__name__},
        )
    if isinstance(value, float) and not value.is_integer():
        raise StateCorruptionError(
            f"card {card!r}: manaValue {value!r} is not an integer",
            context={"card": card, "got": value},
        )
    value = int(value)
    if value < 0:
        raise StateCorruptionError(
            f"card {card!r}: manaValue {value} is negative",
            context={"card": card, "got": value},
        )
    return value


# The five-colour set. A clean MTGJSON file never carries anything else in
# ``colors`` / ``colorIdentity``; anything beyond it is corruption, not a
# new colour to accept.
_LEGAL_COLORS = frozenset("WUBRG")


def ingest_card(raw: dict[str, Any]) -> RawCard:
    """Ingest one MTGJSON v5 card/token dict into a structured :class:`RawCard`.

    Validates the invariants a clean MTGJSON file always holds (a
    well-formed oracle id, a non-empty name, a present type line, text
    present-or-empty, colors within the five-colour set, a non-negative mana
    value) and raises ``StateCorruptionError`` on anything else. Only
    genuinely optional fields default: ``setCode`` to ``None``, ``layout``
    to ``"normal"``. A record missing ``name`` or ``type`` is corruption,
    not a card to guess at.
    """
    if not isinstance(raw, dict):
        raise StateCorruptionError(
            "ingest_card: record is not a dict", context={"got": type(raw).__name__}
        )

    name = _as_str(raw, "name", "")
    if name is None or not name.strip():
        raise StateCorruptionError("card missing name", context={"field": "name"})

    identifiers = raw.get("identifiers")
    if not isinstance(identifiers, dict):
        raise StateCorruptionError(
            f"card {name!r}: no identifiers block", context={"card": name}
        )
    try:
        oracle_id = validate_oracle_id(identifiers.get("scryfallOracleId", ""))
    except ValueError:
        raise StateCorruptionError(
            f"card {name!r}: missing or malformed scryfallOracleId",
            context={"card": name, "got": identifiers.get("scryfallOracleId")},
        ) from None

    # text is present-or-empty: absent (None) and "" are both legal.
    oracle_text = _as_str(raw, "text", name)
    type_line = _as_str(raw, "type", name)
    if type_line is None or not type_line.strip():
        raise StateCorruptionError(
            f"card {name!r}: missing type line", context={"card": name}
        )
    set_code = _as_str(raw, "setCode", name)
    colors = _as_str_tuple(raw, "colors", name)
    if not frozenset(colors) <= _LEGAL_COLORS:
        raise StateCorruptionError(
            f"card {name!r}: colors {colors} outside the five-colour set",
            context={"card": name, "got": colors},
        )

    color_identity_raw = raw.get("colorIdentity")
    if color_identity_raw is None:
        # No colorIdentity field: fall back to the union of colors.
        color_identity = frozenset(colors)
    elif isinstance(color_identity_raw, list) and all(
        isinstance(c, str) for c in color_identity_raw
    ):
        color_identity = frozenset(color_identity_raw)
    else:
        raise StateCorruptionError(
            f"card {name!r}: colorIdentity is not a list of strings",
            context={"card": name, "got": type(color_identity_raw).__name__},
        )
    if not color_identity <= _LEGAL_COLORS:
        raise StateCorruptionError(
            f"card {name!r}: colorIdentity {sorted(color_identity)} outside the "
            "five-colour set",
            context={"card": name, "got": sorted(color_identity)},
        )

    mana_cost_raw = _as_str(raw, "manaCost", name)
    mana_value = _mana_value(raw, name)
    power_raw = _as_str(raw, "power", name)
    toughness_raw = _as_str(raw, "toughness", name)
    loyalty_raw = _as_str(raw, "loyalty", name)
    keywords = _as_str_tuple(raw, "keywords", name)
    types = _as_str_tuple(raw, "types", name)
    subtypes = _as_str_tuple(raw, "subtypes", name)
    supertypes = _as_str_tuple(raw, "supertypes", name)
    layout = _as_str(raw, "layout", name) or "normal"
    # Emblems are their own layout, not tokens: a token is the token layout
    # or carries the Token type.
    is_emblem = layout == "emblem"
    is_token = layout == "token" or "Token" in types
    related_names = _related_names(raw, name)

    identity = CardIdentity(
        oracle_id=oracle_id,
        name=name,
        type_line=type_line,
        set_code=set_code,
        colors=colors,
        mana_cost=mana_cost_raw,
        cmc=mana_value,
        power=power_raw,
        toughness=toughness_raw,
        loyalty=loyalty_raw,
        keywords=keywords,
        oracle_text=oracle_text,
        is_token=is_token,
    )

    return RawCard(
        identity=identity,
        type_line=type_line,
        types=types,
        subtypes=subtypes,
        supertypes=supertypes,
        colors=colors,
        color_identity=color_identity,
        mana_cost_raw=mana_cost_raw,
        mana_value=mana_value,
        power_raw=power_raw,
        toughness_raw=toughness_raw,
        loyalty_raw=loyalty_raw,
        keywords=keywords,
        sentences=split_sentences(oracle_text),
        layout=layout,
        is_token=is_token,
        is_emblem=is_emblem,
        token_name_refs=(),  # by design: see the module docstring
        related_names=related_names,
    )


def _dedup_key(card: RawCard) -> tuple[Any, ...]:
    """The structured identity a duplicate oracle id must match.

    Written out rather than relying on the dataclass's ``!=``: every
    captured field (the :class:`CardIdentity` sub-fields plus the other
    ``RawCard`` fields, a folded ``back_face`` included) and nothing else. A
    reprint that differs only in raw fields the ingest drops (card number,
    uuid, rarity, purchase URLs) is the same card; a duplicate that differs
    in any captured field is corruption.
    """
    identity = card.identity
    return (
        identity.oracle_id,
        identity.name,
        identity.type_line,
        identity.set_code,
        identity.colors,
        identity.mana_cost,
        identity.cmc,
        identity.power,
        identity.toughness,
        identity.loyalty,
        identity.keywords,
        identity.oracle_text,
        identity.is_token,
        card.types,
        card.subtypes,
        card.supertypes,
        card.color_identity,
        card.mana_cost_raw,
        card.mana_value,
        card.power_raw,
        card.toughness_raw,
        card.loyalty_raw,
        card.sentences,
        card.layout,
        card.is_token,
        card.is_emblem,
        card.token_name_refs,
        card.related_names,
        card.back_face,
    )


def _same_card_but_related(a: RawCard, b: RawCard) -> bool:
    """Two printings of one card whose captured fields differ only in ``related_names``."""
    return (
        a.related_names != b.related_names
        and _dedup_key(replace(a, related_names=())) == _dedup_key(replace(b, related_names=()))
    )


def _face_from_record(raw: dict[str, Any], card: RawCard) -> CardFace:
    """Fold an already-ingested face record into structured :class:`CardFace` data.

    ``card`` carries the fields :func:`ingest_card` validated; only the face
    ``name`` is re-derived: ``faceName`` when present, else the half of the
    combined ``"A // B"`` name that follows the separator.
    """
    name = card.identity.name
    face_name = raw.get("faceName")
    if face_name is None:
        if _FACE_NAME_SPLIT in name:
            name = name.rsplit(_FACE_NAME_SPLIT, 1)[-1].strip()
    elif isinstance(face_name, str) and face_name.strip():
        name = face_name
    else:
        raise StateCorruptionError(
            f"card {name!r}: faceName is present but not a non-empty string",
            context={
                "card": name,
                "field": "faceName",
                "got": type(face_name).__name__,
            },
        )
    if not name:
        raise StateCorruptionError(
            f"card {card.identity.name!r}: derived face name is empty",
            context={"card": card.identity.name, "field": "faceName"},
        )
    return CardFace(
        name=name,
        type_line=card.type_line,
        types=card.types,
        subtypes=card.subtypes,
        supertypes=card.supertypes,
        colors=card.colors,
        color_identity=card.color_identity,
        mana_cost_raw=card.mana_cost_raw,
        mana_value=card.mana_value,
        power_raw=card.power_raw,
        toughness_raw=card.toughness_raw,
        loyalty_raw=card.loyalty_raw,
        keywords=card.keywords,
        sentences=card.sentences,
    )


@dataclass
class _FacePair:
    """Mutable per-oracle-id bookkeeping for the modal-DFC fold.

    ``front`` is the first side-``"a"`` record seen (first-wins, like a
    reprint); ``front_key`` is its :func:`_dedup_key`; ``back`` is the
    folded back face once a side-``"b"`` record has arrived.
    """

    front: RawCard
    front_key: tuple[Any, ...]
    back: CardFace | None = None


def _corruption(
    message: str, oracle_id: str, card: RawCard, path: str
) -> StateCorruptionError:
    return StateCorruptionError(
        message,
        context={
            "oracle_id": oracle_id,
            "name_a": card.identity.name,
            "path": path,
        },
    )


def ingest_pool(path: str | Path) -> dict[str, RawCard]:
    """Ingest a whole MTGJSON v5 pool file into an oracle-id-keyed pool.

    Loads ``data.cards`` + ``data.tokens`` and returns ``dict[oracle_id,
    RawCard]`` sorted by card name, then oracle id. Identical reprints
    dedupe to the first and modal-DFC faces fold, as the module docstring
    says. Every other duplicate-oracle-id mismatch raises
    ``StateCorruptionError``: two differing records of one oracle id, two
    differing side-``"a"`` or side-``"b"`` records, a side-``"b"`` with no
    side-``"a"``, or a face record colliding with a normal (side-less)
    record of the same oracle id.
    """
    pool_path = Path(path)
    if not pool_path.is_file():
        raise StateCorruptionError(
            "pool file not found", context={"path": str(pool_path)}
        )
    try:
        doc = json.loads(pool_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StateCorruptionError(
            "pool file is not valid JSON", context={"path": str(pool_path)}
        ) from exc

    data = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(data, dict):
        raise StateCorruptionError(
            "pool file is not MTGJSON v5 (missing top-level 'data')",
            context={"path": str(pool_path)},
        )
    cards = data.get("cards")
    tokens = data.get("tokens")
    if not isinstance(cards, list) or not isinstance(tokens, list):
        raise StateCorruptionError(
            "pool file has no data.cards / data.tokens lists",
            context={"path": str(pool_path)},
        )

    pool: dict[str, RawCard] = {}
    faces: dict[str, _FacePair] = {}
    for raw in [*cards, *tokens]:
        card = ingest_card(raw)
        oracle_id = card.identity.oracle_id
        side = raw.get("side")

        if side is None:
            # Normal (face-less) record.
            if oracle_id in faces:
                raise _corruption(
                    "duplicate oracle id mixes face records and a normal record",
                    oracle_id,
                    card,
                    str(pool_path),
                )
            existing = pool.get(oracle_id)
            if existing is None:
                pool[oracle_id] = card
            elif _same_card_but_related(existing, card):
                # Printings that differ only in relatedCards (ELD's Food tokens list the cards
                # that create them; an alternate-art Ugin, the Ineffable omits its token link):
                # linkage metadata, not characteristics, so keep one record with the union.
                pool[oracle_id] = replace(
                    existing,
                    related_names=tuple(sorted({*existing.related_names, *card.related_names})),
                )
            elif _dedup_key(existing) != _dedup_key(card):
                raise StateCorruptionError(
                    "duplicate oracle id maps to two different cards",
                    context={
                        "oracle_id": oracle_id,
                        "name_a": existing.identity.name,
                        "name_b": card.identity.name,
                        "path": str(pool_path),
                    },
                )
            # else: identical reprint of the same card — keep the first occurrence.
            continue

        if side not in ("a", "b"):
            raise _corruption(
                f"unexpected card face side {side!r}", oracle_id, card, str(pool_path)
            )

        pair = faces.get(oracle_id)
        if pair is None:
            if side != "a" or oracle_id in pool:
                raise _corruption(
                    "face record has no front-face record to fold onto",
                    oracle_id,
                    card,
                    str(pool_path),
                )
            faces[oracle_id] = _FacePair(front=card, front_key=_dedup_key(card))
        elif side == "a":
            # Per-side reprint dedup FIRST; only then does the fold pattern apply.
            if pair.front_key != _dedup_key(card):
                raise _corruption(
                    "two side-a face records map to two different front faces",
                    oracle_id,
                    card,
                    str(pool_path),
                )
            # else: variant printing of the front face — keep the first.
        else:
            face = _face_from_record(raw, card)
            if pair.back is not None and pair.back != face:
                raise _corruption(
                    "two side-b face records map to two different back faces",
                    oracle_id,
                    card,
                    str(pool_path),
                )
            pair.back = face
            pool[oracle_id] = replace(pair.front, back_face=face)

    # A lone side-a record with no side-b partner is not a duplicate at all:
    # it stands as an ordinary single-faced entry (back_face stays None).
    for oracle_id, pair in faces.items():
        if pair.back is None:
            pool[oracle_id] = pair.front

    return dict(sorted(pool.items(), key=lambda item: (item[1].identity.name, item[0])))


def pool_stats(pool: dict[str, RawCard]) -> dict[str, Any]:
    """Aggregate stats over a pool (the coverage denominators come from here).

    Returns a dict with:

    - ``total``           — entries in the pool
    - ``with_text``       — entries with non-empty oracle text
    - ``sentence_total``  — total oracle sentences
    - ``sentence_unique`` — distinct oracle sentences
    - ``keywords``        — keyword -> count histogram (sorted)
    - ``layouts``         — layout -> count histogram (sorted)
    - ``mana_value``      — bucket -> count for "0","1","2","3","4","5+"
    - ``emblems``         — number of emblem-layout entries
    - ``emblem_owners``   — emblem oracle_id -> related names (its owner)
    """
    keywords: dict[str, int] = {}
    layouts: dict[str, int] = {}
    mana_value: dict[str, int] = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5+": 0}
    all_sentences: list[str] = []
    with_text = 0
    emblems = 0
    emblem_owners: dict[str, tuple[str, ...]] = {}
    for card in pool.values():
        if card.identity.oracle_text:
            with_text += 1
        all_sentences.extend(card.sentences)
        for keyword in card.keywords:
            keywords[keyword] = keywords.get(keyword, 0) + 1
        layouts[card.layout] = layouts.get(card.layout, 0) + 1
        bucket = str(card.mana_value) if card.mana_value <= 4 else "5+"
        mana_value[bucket] += 1
        if card.is_emblem:
            emblems += 1
            emblem_owners[card.identity.oracle_id] = card.related_names
    return {
        "total": len(pool),
        "with_text": with_text,
        "sentence_total": len(all_sentences),
        "sentence_unique": len(set(all_sentences)),
        "keywords": dict(sorted(keywords.items())),
        "layouts": dict(sorted(layouts.items())),
        "mana_value": mana_value,
        "emblems": emblems,
        "emblem_owners": dict(sorted(emblem_owners.items())),
    }
