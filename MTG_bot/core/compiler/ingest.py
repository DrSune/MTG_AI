"""Structured ingest of MTGJSON v5 pool files (compiler step 1).

The compiler's first job is to turn an MTGJSON v5 dump into structured
per-card records BEFORE any template matching, so that nothing downstream
ever reads an English string for meaning (PITFALLS: "English substrings
cannot be the IR"). This module keeps only what is structured:

- ``CardIdentity`` (core/identity.py), keyed on
  ``identifiers.scryfallOracleId`` — the oracle id is the primary key
  everywhere; volatile card numbers and per-printing uuids never become
  keys or fields (PITFALLS: "Re-ingest must not invalidate learned state").
- Printed characteristics as structured fields: type line / types /
  subtypes / supertypes, colours, colour identity, the mana cost string,
  the mana value as an int, P/T and loyalty as the printed strings,
  keywords.
- The oracle text split into a deterministic sentence tuple (``sentences``)
  — that tuple is the template compiler's input. The split is
  paren-depth-aware: ``[.?!] + whitespace`` splits only at paren depth 0,
  so a multi-sentence parenthetical reminder ("Opt (Look at the top card of
  your library. You may put that card on the bottom.)") stays ONE sentence,
  while single-sentence reminders and line-break ability boxes behave as
  before (see ``split_sentences`` and the 2026-09-15 re-measured baseline).

Deliberate non-goals:

- No NLP. ``token_name_refs`` is ``()`` by construction. Token names in
  this pool are bare subtype words ("Angel", "Knight", "Treasure"), so a
  bare string occurrence in the text is not a reliable token-creation
  signal — "is a Knight in addition to its other types" (a subtype grant)
  is not creating a Knight token. The reliable pattern is the whole
  "create a 1/1 white Bird creature token" sentence template, and matching
  that belongs to the template compiler (Phase 1 step 3), not to the
  structured ingest. The spec's honesty clause applies: detection is fuzzy,
  so the field is an honest empty tuple.
- ``UnknownCardError`` is not raised here: ingest stores no cross-card
  references, so there is no reference to an unknown card to fail on.
  Malformed data that should be impossible in a clean MTGJSON file is
  ``StateCorruptionError``.

Reprint duplicates (documented design decision):

   The M21 pool file is not a clean single-set MTGJSON dump: it appends
   reprint printings, so the same card — every captured field identical,
   differing only in raw fields the ingest drops (card number, uuid,
   rarity, …) — can appear more than once (measured 2026-09-15: 112 of its
   397 card records repeat an oracle id). The oracle id names the card,
   not the printing, so ``ingest_pool`` dedupes *identical* duplicates to
   one entry (first occurrence wins — deterministic, "identical" per
   :func:`_dedup_key`) instead of failing, and raises
   ``StateCorruptionError`` only when the same oracle id maps to two
   DIFFERENT card records, which is genuine corruption.

Modal-DFC face fold (documented design decision, KNOWLEDGE/2026-10-18/92):

   MTGJSON stores each face of a ``modal_dfc`` card as its own record with
   ``side`` ``"a"`` / ``"b"``, sharing the oracle id. ``ingest_pool`` folds
   exactly that pattern — one side-``"a"`` record becomes the ``RawCard``,
   one side-``"b"`` record becomes its structured ``back_face`` (zero-loss,
   §11) — after the per-side reprint dedup above. Every other
   duplicate-oracle-id mismatch still raises ``StateCorruptionError``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from MTG_bot.core.errors import StateCorruptionError
from MTG_bot.core.identity import CardIdentity, validate_oracle_id

# Sentence split: a sentence ends at ``[.?!]`` followed by whitespace (at
# paren depth 0), or at a line break (always). No NLP — deterministic by
# construction.
#
# The rule is PAREN-DEPTH-AWARE (fix 2026-09-15, adversarial review):
# ``[.?!] + whitespace`` splits ONLY when the paren depth is zero. A
# multi-sentence parenthetical reminder like
#   Opt (Look at the top card of your library. You may put that card on
#   the bottom.)
# is ONE sentence: the internal period+space sits at depth 1, so the naive
# regex ``(?<=[.?!])\s+`` used to break it into two unbalanced chunks
# ("…library." / "You may put that card on the bottom.)") — 23 of the 397
# M21 card records affected (measured 2026-09-15): Temple of Epiphany /
# Malady / Mystery / Silence / Triumph ×2 each, Speaker of the Heavens ×2,
# Discontinuity ×2, Mazemind Tome ×2, and Opt, Riddleform, Spined
# Megalodon, Wall of Runes, Alchemist's Gift, Malefic Scythe, Short Sword
# ×1 each. Tokens: 0 affected.
#
# Single-sentence parentheticals ("Flying (Attacking doesn't cause this
# creature to tap.)") stay one sentence: their only period is inside the
# parens, so the old behaviour is preserved by the new rule, not by
# accident. Line breaks still split at any depth (ability boxes).
_SENTENCE_END_CHARS = frozenset(".?!")
_WHITESPACE = frozenset(" \t\r\n")


def split_sentences(text: str | None) -> tuple[str, ...]:
    """Split oracle text into a deterministic sentence tuple.

    Split at line breaks (any paren depth) and at ``[.?!]`` followed by
    whitespace — but the latter only when the paren depth is zero, so a
    multi-sentence parenthetical reminder stays one sentence. Chunks are
    stripped, empties dropped. ``None`` / blank text gives ``()`` — basic
    lands and the few cards printed without a text box in this dump.

    Paren depth is tracked over the raw text: ``(`` opens, ``)`` closes
    (never below zero, so a stray ``)`` cannot poison the depth).
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
            # Line breaks split at any depth.
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
            # Sentence boundary: punctuation followed by at least one
            # whitespace char at depth 0 (the old ``\s+`` lookahead, exactly).
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
    keyed on. ``back_face`` is ``None`` for every single-faced card (zero
    behavior change for such cards) and the structured back face for a
    modal DFC folded by :func:`ingest_pool`.
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


def _as_str(
    raw: dict[str, Any], key: str, card: str, *, default: str | None = None
) -> str | None:
    """Read an optional string field, raising on wrong type or missing required."""
    value = raw.get(key)
    if value is None:
        return default
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
    *names*; this M21 dump instead fills ``tokens`` with record *uuids*
    while ``reverseRelated`` carries names. Either way the linkage is
    structured (no NLP), so :class:`RawCard` keeps the raw union verbatim —
    for the pool's three emblems that union is exactly their owner names
    (their only key is ``reverseRelated``), which is what the dropped
    emblem→owner association needed.
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

    Lands, tokens and other no-cost cards carry no ``manaValue`` — they are
    0, never ``None`` (the spec's mana_value histogram has a 0 bucket).
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

    Validates the invariants a clean MTGJSON file always holds — a
    well-formed oracle id (via :func:`validate_oracle_id`), a non-empty
    name, a present type line, text present-or-empty, colors within the
    five-colour set, non-negative mana value — and raises
    ``StateCorruptionError`` on anything else. The returned record is
    frozen; its identity is keyed on the oracle id.

    Documented defaults (genuinely optional fields only): ``setCode``
    defaults to ``None`` and ``layout`` defaults to ``"normal"`` when
    absent. ``name`` and ``type`` are REQUIRED — a record missing either
    is corruption, not a card to guess at.
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
    layout = _as_str(raw, "layout", name, default="normal") or "normal"
    # Emblems are their own layout (three in this pool), NOT tokens: a token
    # is the token layout or a Token subtype. Measured 2026-09-15: all 17
    # token-layout records carry "Token" in types, no normal-layout record
    # does, and no token-layout record is an emblem.
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
        # () by design — see the module docstring ("Deliberate non-goals"):
        # exact-occurrence detection of bare-word token names is unreliable,
        # and token-creation belongs to the template compiler.
        token_name_refs=(),
        # Structured linkage verbatim (see _related_names): the only
        # cross-record association this pool file carries. For the three
        # emblems it is exactly their owner names.
        related_names=related_names,
    )


def _dedup_key(card: RawCard) -> tuple[Any, ...]:
    """The structured identity a duplicate oracle id must match.

    Explicit and written down in one place (rather than relying on the
    dataclass's ``!=``): dedup keys on EVERY captured field — the
    :class:`CardIdentity` sub-fields plus the remaining ``RawCard``
    fields (including a folded ``back_face``) — and on nothing else. A
    reprint that differs only in raw fields the ingest deliberately drops
    (card number, uuid, rarity, purchase URLs, …) is still the same card;
    a duplicate that differs in any captured field is corruption.
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


def _same_token_but_creators(a: RawCard, b: RawCard) -> bool:
    """Two printings of one token whose captured fields differ only in ``related_names``."""
    return (
        a.is_token
        and b.is_token
        and a.related_names != b.related_names
        and _dedup_key(replace(a, related_names=())) == _dedup_key(replace(b, related_names=()))
    )


def _face_from_record(raw: dict[str, Any], card: RawCard) -> CardFace:
    """Fold an already-ingested face record into structured :class:`CardFace` data.

    Reuses the exact :func:`ingest_card` pipeline (``card`` carries the
    validated fields and the :func:`split_sentences` output); only the
    face ``name`` is re-derived: ``faceName`` when present, else the half
    of the combined ``"A // B"`` name that follows the separator.
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

    Loads ``data.cards`` + ``data.tokens`` from the file and returns
    ``dict[oracle_id, RawCard]`` in stable deterministic order (sorted by
    card name, then oracle id).

    Duplicate oracle ids: the M21 pool file appends reprint printings, so
    the same card (every captured field identical, differing only in raw
    fields the ingest drops — card number, uuid, rarity, …) can appear
    more than once. The oracle id names the card, not the printing, so
    such duplicates dedupe to one entry (first occurrence wins —
    deterministic); what counts as "the same card" is :func:`_dedup_key`.
    A duplicate oracle id whose captured records DIFFER is genuine
    corruption and raises ``StateCorruptionError``.

    The ONE exception is the modal-DFC face pattern (KNOWLEDGE/2026-10-18
    /92): MTGJSON stores each face of a ``layout == "modal_dfc"`` card as
    its own record with ``side == "a"`` / ``"b"``, sharing the oracle id
    and DIFFERING in every captured field. Exactly one side-``"a"`` record
    (per side after the reprint dedup above) becomes the :class:`RawCard`,
    and exactly one side-``"b"`` record folds into its ``back_face`` —
    zero-loss (§11), never dropped. Every other duplicate-oracle-id
    mismatch keeps raising ``StateCorruptionError``: two differing
    side-``"a"`` records, two differing side-``"b"`` records, a side-``"b"``
    with no side-``"a"``, or a face record colliding with a normal
    (side-less) record of the same oracle id.
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
            # Normal (face-less) record: the pre-ZNR path, byte-for-byte.
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
            elif _same_token_but_creators(existing, card):
                # B-39: printings of one token (ELD Food x4, IKO Human Soldier) differ only in
                # relatedCards.reverseRelated, the OTHER cards that create it. That is a fact about
                # those cards, not this token's characteristics, so keep one record with the union.
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
    """Aggregate stats over a pool — the KNOWLEDGE/NUMBERS.md baseline check.

    Returns a dict with:

    - ``total``           — entries in the pool
    - ``with_text``       — entries with non-empty oracle text
    - ``sentence_total``  — total oracle sentences
    - ``sentence_unique`` — distinct oracle sentences
    - ``keywords``        — keyword -> count histogram (sorted)
    - ``layouts``         — layout -> count histogram (sorted)
    - ``mana_value``      — bucket -> count for "0","1","2","3","4","5+"
    - ``emblems``         — number of emblem-layout entries
    - ``emblem_owners``   — emblem oracle_id -> related names (owner names;
                            for the pool's three emblems the only
                            ``relatedCards`` key is ``reverseRelated``, so
                            this is the emblem -> owner association)
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
